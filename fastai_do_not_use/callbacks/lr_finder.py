"Tools to help find the optimal learning rate for training"
from ..torch_core import *
from ..data import DataBunch
from ..callback import *
from ..basic_train import Learner, LearnerCallback

__all__ = ['LRFinder']

class LRFinder(LearnerCallback):
    "Explore lr vs loss relationship for a learner"
    def __init__(self, learn:Learner, start_lr:float=1e-5, end_lr:float=10, num_it:int=200):
        "Initialize schedule of learning rates"
        super().__init__(learn)
        self.data = learn.data
        self.sched = Stepper((start_lr, end_lr), num_it, annealing_exp)
        #To avoid validating if the train_dl has less than num_it batches, we put aside the valid_dl and remove it
        #during the call to fit.
        self.valid_dl = learn.data.valid_dl
        self.data.valid_dl = None

    def on_train_begin(self, **kwargs:Any)->None:
        "init optimizer and learn params"
        self.learn.save('tmp')
        self.opt = self.learn.opt
        self.opt.lr = self.sched.start
        self.stop,self.best_loss = False,0.

    def on_batch_end(self, iteration:int, smooth_loss:TensorOrNumber, **kwargs:Any)->None:
        "Determine if loss has runaway and we should stop"
        if iteration==0 or smooth_loss < self.best_loss: self.best_loss = smooth_loss
        self.opt.lr = self.sched.step()
        if self.sched.is_done or smooth_loss > 4*self.best_loss:
            #We use the smoothed loss to decide on the stopping since it's less shaky.
            self.stop=True
            return True

    def on_epoch_end(self, **kwargs:Any)->None:
        "Tell Learner if we need to stop"
        return self.stop

    def on_train_end(self, **kwargs:Any)->None:
        "Cleanup learn model weights disturbed during LRFind exploration"
        # restore the valid_dl we turned of on `__init__`
        self.data.valid_dl = self.valid_dl
        self.learn.load('tmp')
