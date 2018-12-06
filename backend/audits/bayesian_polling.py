# pylint: disable=E0402

from .shared_objects.arrange_candidates import get_winners
from .bptools.bptools import compute_win_probs

class BayesianPolling():
    """ Bayesian ballot-polling audit in Python
    A wrapper class around Ron Rivest's [2018-bptool](https://github.com/ron-rivest/2018-bptool).
    """
    def __init__(self, votes_array, num_ballots, num_winners,\
            risk_limit, seed, sample_tallies):
        super().__init__()
        assert all(votes >= 0 for votes in votes_array)
        self.votes_array = votes_array
        assert num_ballots >= sum(votes_array)
        self.num_ballots = num_ballots
        assert num_winners < len(votes_array)
        self.num_winners = num_winners
        self.sample_tallies = sample_tallies
        assert 0. < risk_limit <= 1.
        self.risk_limit = risk_limit
        self.seed = seed

    def bayesian_polling_audit(self):
        """
        Uses compute_win_probs to verify the election results.
        Returns true IFF the reported winners and Bayesian projected
        winners match AND the probability of each projected winner
        winning is greater than the significance level.
        """
        reported_winners = get_winners(self.votes_array, self.num_winners)
        bayesian_winners = compute_win_probs([self.sample_tallies],\
                self.num_ballots, self.num_winners, self.seed)
        reported_set = {w for w in reported_winners}
        bayesian_set = {w.i for w in bayesian_winners}
        for projected, reported in zip(bayesian_winners, reported_winners):
            if not(len(bayesian_winners) == len(reported_winners)\
                    and (projected.i in reported_set)\
                    and (reported in bayesian_set)\
                    and (projected.p >= 1 - self.risk_limit)):
                return False
        return True

    def run_audit(self):
        audit_result = self.bayesian_polling_audit()

        if audit_result:
            self.IS_DONE_MESSAGE = "Audit completed: the results stand."
            self.IS_DONE_FLAG = "success"
        else:
            self.IS_DONE_MESSAGE = "Failed to confirm the results. Sample a larger portion of the ballots. This may indicate that your reported winners are incorrect."
            self.IS_DONE_FLAG = "danger"