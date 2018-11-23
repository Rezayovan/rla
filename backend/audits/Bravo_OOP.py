import numpy as np
import threading
import random
import queue

class Candidates:
    def __init__(self, winners_in, losers_in):
        self.winners = winners_in
        self.losers = losers_in

class Hypotheses:
    def __init__(self, test_stat_in, reject_count_in):
        self.test_stat = test_stat_in
        self.reject_count = reject_count_in

class Bravo:
    def __init__(self, votes_array, num_ballots, num_winners,
                risk_limit, seed, max_tests):

                # global vars
                self._VOTES_BUFFER = queue.Queue()
                self._LOCK = threading.Lock()
                self._CV = threading.Condition(self._LOCK)

                # status vars
                self.IS_DONE = False
                self.IS_DONE_MESSAGE = ""

                # audit variables
                self.votes_array = votes_array
                self.num_ballots = num_ballots
                self.num_winners = num_winners
                self.risk_limit = risk_limit

                # Need random.Random() instance per Bravo class instance
                # Can then seed this random number object directly
                self.random_gen = random.Random()
                self.seed = seed
                self.random_gen.seed(seed)

                self.max_tests = max_tests
                self.num_candidates = len(votes_array)

                # Ensure parameters make sense
                assert 0 < num_winners <= self.num_candidates
                assert 0. < risk_limit <= 1.
                assert all(votes >= 0 for votes in votes_array)
                if self.max_tests <= 0:
                    self.max_tests = sum(self.votes_array)
                else:
                    self.max_tests = min(self.max_tests, sum(self.votes_array))

                self.candidates = None
                self.hypotheses = None
                self.margins = None
                self.audit_result = None

    def append_votes_buffer(self, vote):
        cv = self._CV
        buffer = self._VOTES_BUFFER

        cv.acquire()
        buffer.put(vote)
        cv.notify()
        cv.release()

    def get_votes(self):
        cv = self._CV
        buffer = self._VOTES_BUFFER

        cv.acquire()
        print("getting vote")
        while buffer.empty():
            print("wait condition")
            cv.wait()
        votes = buffer.get()
        cv.release()

        return votes

    def arrange_candidates(self):
        """
        From `votes_array`, we can find the winners as the `num_winners` candidates
        (indices) with the most votes. The losers are the rest of the candidates.
        """
        votes_array = self.votes_array
        num_winners = self.num_winners

        sorted_candidates = sorted(enumerate(votes_array), key=lambda t: t[1], reverse=True)
        winners = set(t[0] for t in sorted_candidates[:num_winners])
        losers = set(t[0] for t in sorted_candidates[num_winners:])

        return Candidates(winners, losers)

    def get_margins(self):
        """
        Let `margins[winner][loser] ≡ VOTES[winner]/(VOTES[winner] + VOTES[loser])`
        be the fraction of votes `winner` was reported to have received among
        ballots reported to show a vote for `winner` or `loser` or both.
        """
        candidates = self.candidates
        votes_array = self.votes_array
        num_candidates = self.num_candidates
        self.margins = np.zeros([num_candidates, num_candidates])
        margins = self.margins

        for winner in candidates.winners:
            for loser in candidates.losers:
                margins[winner][loser] = votes_array[winner] \
                        / (votes_array[winner] + votes_array[loser])

        return margins

    def get_sequence_number(self):
        """Returns random sequence number to draw ballot from."""
        num_ballots = self.num_ballots
        ballot_to_draw = self.random_gen.randint(1, num_ballots)
        return ballot_to_draw

    def get_ballot(self):
        """ Step 2 of the BRAVO algorithm.
        Randomly picks a ballot to test and returns a list of its votes.
        The ballot picked is returned to the frontend for the user to input
        actual votes on the ballot. The ballot should be selected using a
        random function seeded by a user-generated seed.
        Note: 'random' should be seeded before this function is called.
        """
        num_winners = self.num_winners
        ballot_votes = self.get_votes()

        if len(ballot_votes) <= num_winners:
            return []
        return ballot_votes

    def update_hypothesis(self, winner, loser):
        """ Step 5 of the BRAVO algorithm.
        Rejects the null hypothesis corresponding to the test statistic of
        the `winner` and `loser` pair. Increments the null hypothesis
        rejection count.
        """
        hypotheses = self.hypotheses
        risk_limit = self.risk_limit
        if hypotheses.test_stat[winner][loser] >= 1/risk_limit:
            hypotheses.test_stat[winner][loser] = 0
            hypotheses.reject_count += 1

    def update_audit_stats(self, vote):
        """ Steps 3-5 from the BRAVO algorithm.
        Updates the `test_statistic` and rejects the corresponding null
        hypothesis when appropriate.
        """
        candidates = self.candidates
        hypotheses = self.hypotheses
        margins = self.margins
        if vote in candidates.winners: # Step 3
            for loser in candidates.losers:
                hypotheses.test_stat[vote][loser] *= 2*margins[vote][loser]
                self.update_hypothesis(vote, loser)
        elif vote in candidates.losers: # Step 4
            for winner in candidates.winners:
                hypotheses.test_stat[winner][vote] *= 2*(1-margins[winner][vote])
                self.update_hypothesis(winner, vote)

    def run_audit(self):
        """
        Runs the algorithm given in "BRAVO" (2012) §7.
        """
        candidates = self.candidates
        num_winners = len(candidates.winners)
        num_losers = len(candidates.losers)
        num_candidates = num_winners + num_losers
        max_tests = self.max_tests

        test_statistic = np.ones([num_candidates, num_candidates])
        reject_count = 0
        num_null_hypotheses = num_winners * num_losers
        hypotheses = Hypotheses(test_statistic, reject_count)

        ballots_tested = 0

        while ballots_tested < max_tests: # Step 6
            ballot_votes = self.get_ballot()
            assert all(0 <= vote < num_candidates for vote in ballot_votes)
            for vote in ballot_votes:
                self.update_audit_stats(vote)
            ballots_tested += 1
            print(ballots_tested)

            # Step 6
            if hypotheses.reject_count >= num_null_hypotheses:
                return True

        return False

    def bravo(self):
        """BRAVO Ballot-Polling Audit Implementation
        Given an array of votes cast, the number of winners, a risk limit, and a
        maximum number of ballots to test, `bravo` runs an audit on the election
        results to confirm with `risk_limit` confidence that the reported
        `num_winners` winner(s) are indeed the winners.
        """
        self.candidates = self.arrange_candidates()
        self.margins = self.get_margins()
        self.audit_result = self.run_audit()
        self.IS_DONE = True

        print("audit has been finished")
        if self.audit_result:
            self.IS_DONE_MESSAGE = "Audit completed: the results stand."
        else:
            self.IS_DONE_MESSAGE = "Too many ballots tested. Perform a full hand-recount of the ballots."