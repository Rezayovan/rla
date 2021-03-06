import random
import math
import numpy as np
from .shared_objects.BaseAudit import BaseAudit
from .shared_objects.Candidates import Candidates
from .shared_objects.Hypotheses import Hypotheses
import json
import copy

class Cast(BaseAudit):

    def __init__(self, initial_cvr_data, num_candidates,
                 num_winners, num_stages, batch_size,
                num_batches, risk_tolerance, threshold, random_seed):
        super().__init__()
        self.num_candidates = num_candidates
        assert 1. <= num_winners <= num_candidates
        self.num_winners = num_winners
        self.num_stages = num_stages
        self.batch_size = batch_size
        self.num_batches = num_batches
        self.num_unaudited = num_batches
        self.threshold = threshold
        self.random_seed = random_seed
        self.unaudited = np.arange(num_batches)
        self.alpha = self.calc_alpha_s(risk_tolerance)
        self.cvr_batches = initial_cvr_data
        self.reported_batch_info, self.audited_batch_info, self.winners, self.losers = self.init_info()
        self.random_gen = random.Random()
        self.random_gen.seed(int(random_seed))
        # this is for getting a random sequence number
        # TODO: NEED TO CHANGE OR ELSE WILL FORGET WHY ITS HERE
        self.num_ballots = self.num_batches
        self.sequence_order = []
        self.STAGE_MESSAGE = ""

    def get_sequence_number(self):
        self._CV.acquire()
        while not self.sequence_order:
            self._CV.wait()
        sequence_number = self.sequence_order.pop(0)
        self._CV.release()
        print("sequence number", sequence_number)
        return sequence_number+1

    def calc_alpha_s(self, risk_tolerance):
        diff = 1 - risk_tolerance
        diff_s = diff ** (1/float(self.num_stages))
        alpha_s = 1 - diff_s
        return alpha_s

    def init_info(self):
        total_votes = np.zeros(self.num_candidates)
        reported_batch_info = []
        get_batch_generator = self.get_batch_first()
        for batch_info in get_batch_generator:
            reported_batch_info.append(batch_info)
            for idx, num_votes in enumerate(batch_info):
                total_votes[idx] = total_votes[idx] + num_votes

        losers = np.argsort(total_votes)[:(self.num_candidates - self.num_winners)]
        winners = np.argsort(total_votes)[(self.num_candidates - self.num_winners):]
        reported_batch_info = np.asarray(reported_batch_info)
        audited_batch_info = np.zeros(reported_batch_info.shape)

        return reported_batch_info, audited_batch_info, winners, losers

    def get_batch_info(self):
        '''
        Get batch info
        '''
        return json.loads(self.get_votes())

    def get_batch_first(self):
        '''
        Get batch info for beginning of audit.
        '''
        for batch in self.cvr_batches:
            yield batch

    def calc_adj_margin(self, winner, loser):
        reported_margin = 0
        audited_margin = 0
        for num in self.unaudited:
            reported_margin = reported_margin + self.reported_batch_info[num][winner] - self.reported_batch_info[num][loser]

        for batches in self.audited_batch_info:
            audited_margin = audited_margin + batches[winner] - batches[loser]

        return reported_margin + audited_margin

    '''
    Calculates the maximun overstatement for each batch of ballots
    Batches that have been audited will have a max overstatmennt of 0
    '''
    def calc_u_ps(self):
        u_ps = np.zeros(self.num_batches)

        # Matrix containing all the adj margins between any winner and any loser
        adj_margins = np.zeros([len(self.winners), len(self.losers)])

        for idw, winner in enumerate(self.winners):
            for idl, loser in enumerate(self.losers):
                adj_margins[idw][idl] = self.calc_adj_margin(winner, loser)

        for batch_num in self.unaudited:
            max_u_p = []
            for idw, winner in enumerate(self.winners):
                for idl, loser in enumerate(self.losers):
                    if(adj_margins[idw][idl] == 0):
                        u_p = 0
                    else:
                        u_p = (self.reported_batch_info[batch_num][winner] - self.reported_batch_info[batch_num][loser] + self.batch_size) / adj_margins[idw][idl]
                    max_u_p.append(u_p)
            u_ps[batch_num] = np.amax(max_u_p)
        return u_ps


    '''
    Calculates the threshold for how many batches need to be audited for this stage
    '''
    def calc_T(self):
        u_ps = self.calc_u_ps()
        t_ps = []
        squigglie_u_ps = []
        for u_p in u_ps:
            if(u_p < self.threshold):
                t_ps.append(u_p)
                squigglie_u_ps.append(0.0)
            else:
                t_ps.append(self.threshold)
                squigglie_u_ps.append(u_p - self.threshold)
        T = sum(t_ps)
        squigglie_u_ps = np.asarray(squigglie_u_ps)
        print("T", T)
        print("t_ps", t_ps)
        print("u_ps", u_ps)
        print("squigglie_u_ps", squigglie_u_ps)
        return T, squigglie_u_ps

    '''
    Returns the number of squigle u_ps needed to add up to 1-T
    '''
    def calc_n(self, T, squigglie_u_ps):
        sorted_squigglie_u_ps = np.argsort(squigglie_u_ps)
        sorted_squigglie_u_ps = sorted_squigglie_u_ps[::-1]
        print(squigglie_u_ps)
        print(sorted_squigglie_u_ps)
        sum = 0
        count = 0
        while sum < (1 - T):
            if count > self.num_unaudited:
                return count
            sum += squigglie_u_ps[sorted_squigglie_u_ps[count]]
            count += 1

        base = (self.num_unaudited - count) / self.num_unaudited
        n = math.log(self.alpha, base)
        n = math.ceil(n)
        print("count", count)
        print("N_s", self.num_unaudited)
        print("Base", base)
        print("alpha_s", self.alpha)
        return n

    def calc_t_s(self, batches_to_audit, adj_margins):
        e_wlp = []
        for batch_num in batches_to_audit:
            for idw, w in enumerate(self.winners):
                for idl, l in enumerate(self.losers):
                    print("calc_t_s batch_num", batch_num)
                    reported = self.reported_batch_info[batch_num][w] - self.reported_batch_info[batch_num][l]
                    audited = self.audited_batch_info[batch_num][w] - self.audited_batch_info[batch_num][l]
                    print(reported, audited)
                    e_wlp.append((reported - audited)/ adj_margins[idw][idl])
        print(e_wlp)
        return np.amax(e_wlp)

    def run_audit(self):
        try:
            random.seed(a = self.random_seed)

            for i in range(self.num_stages):
                self.STAGE_MESSAGE = "Starting stage {}".format(i)
                T, squigglie_u_ps = self.calc_T()
                n = self.calc_n(T, squigglie_u_ps)
                print("Number of batches to audit: ", n)

                if(len(self.unaudited) < n):
                    # fills sequence_order list w/ dummy values
                    # so frontend can check if audit completed
                    self._CV.acquire()
                    self.sequence_order = [1, 1, 1, 1, 1]
                    self._CV.notify()
                    self._CV.release()
                    # end of bs code
                    print('More batches to audit then provided preform a full hand recount')
                    self.IS_DONE_MESSAGE = "Audit requires more batches than remaining. Perform a full hand-recount of the ballots."
                    self.IS_DONE_FLAG = "danger"
                    self.IS_DONE = True
                    return
                batches_to_audit = random.sample(list(self.unaudited), n)
                print(batches_to_audit)
                self._CV.acquire()
                self.sequence_order = batches_to_audit
                self._CV.notify()
                self._CV.release()

                adj_margins = np.zeros([len(self.winners), len(self.losers)])

                for idw, winner in enumerate(self.winners):
                    for idl, loser in enumerate(self.losers):
                        adj_margins[idw][idl] = self.calc_adj_margin(winner, loser)

                print("Batches to audit", batches_to_audit)
                self.num_unaudited = self.num_unaudited - n
                self.unaudited = self.unaudited.tolist()
                self.batches_to_audit = random.sample(list(self.unaudited), n)
                for batch_num in self.batches_to_audit:
                    print("batch_nun", batch_num)
                    print("batch list", self.batches_to_audit)
                    self.unaudited.remove(batch_num)
                    self.audited_batch_info[batch_num] = self.get_batch_info()
                self.unaudited = np.asarray(self.unaudited)

                print("Got all info")
                t_s = self.calc_t_s(self.batches_to_audit, adj_margins)
                print("t_s", t_s)

                if t_s < self.threshold:
                    print('Audit complete')
                    self.IS_DONE_MESSAGE = "Audit completed: the results stand."
                    self.IS_DONE_FLAG = "success"
                    self.IS_DONE = True
                    return

            print('Audit failed. Full hand recount needed')
            self.IS_DONE_MESSAGE = "Audit cannot verify the election results. Perform a full hand-recount of the ballots."
            self.IS_DONE_FLAG = "danger"
            self.IS_DONE = True
            return
        except:
            return "Exception Raised"

# num_candidates, num_winners, num_stages, batch_size
# num_batches, risk_tolerance, threshold, random_seed

if __name__ == "__main__":
    num_candidates, num_winners, num_stages, batch_size = (2, 1, 2, 10)
    num_batches, risk_tolerance, threshold, random_seed = (20, .05, .01, 1234567)
    params = [num_candidates, num_winners, num_stages, batch_size,
    num_batches, risk_tolerance, threshold, random_seed]
    cast = Cast(*params)
    cast.run_audit()
