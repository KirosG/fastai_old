
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################
        # file to edit: /data1/jhoward/git/fastai_v1/dev_nb/004a_discriminative_lr.ipynb

from nb_004 import *

def requires_grad(l, b=None):
    ps = list(l.parameters())
    if not ps: return None
    if b is None: return ps[0].requires_grad
    for p in ps: p.requires_grad=b

def trainable_params(m): return filter(lambda p: p.requires_grad, m.parameters())

class OptimWrapper():
    "Basic wrapper around an optimizer to simplify HP changes"
    def __init__(self, opt:optim.Optimizer, wd:Floats=0., true_wd:bool=False):
        self.opt,self.true_wd = opt,true_wd
        self.opt_keys = list(self.opt.param_groups[0].keys())
        self.opt_keys.remove('params')
        self.read_defaults()
        self.wd = wd

    @classmethod
    def create(cls, opt_fn, lr, layer_groups, **kwargs):
        opt = opt_fn([{'params': trainable_params(l), 'lr':0} for l in layer_groups])
        opt = cls(opt, **kwargs)
        opt.lr = listify(lr, layer_groups)
        return opt

    def __repr__(self) -> str:
        return f'OptimWrapper over {repr(self.opt)}.\nTrue weight decay: {self.true_wd}'

    #Pytorch optimizer methods
    def step(self):
        # weight decay outside of optimizer step (AdamW)
        if self.true_wd:
            for lr,wd,pg in zip(self._lr,self._wd,self.opt.param_groups):
                for p in pg['params']: p.data.mul_(1 - wd*lr)
            self.set_val('weight_decay', listify(0, self._wd))
        self.opt.step()

    def zero_grad(self): self.opt.zero_grad()

    #Hyperparameters as properties
    @property
    def lr(self) -> float: return self._lr[-1]

    @lr.setter
    def lr(self, val:float): self._lr = self.set_val('lr', listify(val, self._lr))

    @property
    def mom(self) -> float: return self._mom[-1]

    @mom.setter
    def mom(self, val:float):
        if 'momentum' in self.opt_keys: self.set_val('momentum', listify(val, self._mom))
        elif 'betas' in self.opt_keys:  self.set_val('betas', (listify(val, self._mom), self._beta))
        self._mom = listify(val, self._mom)

    @property
    def beta(self) -> float: return None if self._beta is None else self._beta[-1]

    @beta.setter
    def beta(self, val:float):
        if val is None: return
        if 'betas' in self.opt_keys:    self.set_val('betas', (self._mom, listify(val, self._beta)))
        elif 'alpha' in self.opt_keys:  self.set_val('alpha', listify(val, self._beta))
        self._beta = listify(val, self._beta)

    @property
    def wd(self) -> float: return self._wd[-1]

    @wd.setter
    def wd(self, val:float):
        if not self.true_wd: self.set_val('weight_decay', listify(val, self._wd))
        self._wd = listify(val, self._wd)

    #Helper functions
    def read_defaults(self):
        "Read the values inside the optimizer for the hyper-parameters"
        self._beta = None
        if 'lr' in self.opt_keys: self._lr = self.read_val('lr')
        if 'momentum' in self.opt_keys: self._mom = self.read_val('momentum')
        if 'alpha' in self.opt_keys: self._beta = self.read_val('alpha')
        if 'betas' in self.opt_keys: self._mom,self._beta = self.read_val('betas')
        if 'weight_decay' in self.opt_keys: self._wd = self.read_val('weight_decay')

    def set_val(self, key:str, val):
        "Set the values inside the optimizer dictionary at the key"
        if is_tuple(val): val = [(v1,v2) for v1,v2 in zip(*val)]
        for v,pg in zip(val,self.opt.param_groups): pg[key] = v
        return val

    def read_val(self, key:str) -> Union[List[float],Tuple[List[float],List[float]]]:
        "Read a hyper-parameter key in the optimizer dictionary."
        val = [pg[key] for pg in self.opt.param_groups]
        if is_tuple(val[0]): val = [o[0] for o in val], [o[1] for o in val]
        return val

flatten_model=lambda l: sum(map(flatten_model,l.children()),[]) if len(list(l.children())) else [l]
def first_layer(m): return flatten_model(m)[0]

def split_model_idx(model, idxs):
    "Split the model according to the indices in [idxs]"
    layers = flatten_model(model)
    if idxs[0] != 0: idxs = [0] + idxs
    if idxs[-1] != len(layers): idxs.append(len(layers))
    return [nn.Sequential(*layers[i:j]) for i,j in zip(idxs[:-1],idxs[1:])]

def split_model(model, splits, want_idxs=False):
    "Split the model according to the layers in [splits]"
    layers = flatten_model(model)
    idxs = [layers.index(first_layer(s)) for s in listify(splits)]
    res = split_model_idx(model, idxs)
    return (res,idxs) if want_idxs else res

bn_types = (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)

def set_bn_eval(m):
    for l in m.children():
        if isinstance(l, bn_types) and not next(l.parameters()).requires_grad:
            l.eval()
        set_bn_eval(l)

@dataclass
class BnFreeze(Callback):
    learn:Learner
    def on_epoch_begin(self, **kwargs): set_bn_eval(self.learn.model)

def even_mults(start, stop, n):
    mult = stop/start
    step = mult**(1/(n-1))
    return np.array([start*(step**i) for i in range(n)])

@dataclass
class Learner():
    "Object that wraps together some data, a model, a loss function and an optimizer"
    data:DataBunch
    model:nn.Module
    opt_fn:Callable=AdamW
    loss_fn:Callable=F.cross_entropy
    metrics:Collection[Callable]=None
    true_wd:bool=True
    wd:Floats=1e-6
    train_bn:bool=True
    path:str = 'models'
    callback_fns:Collection[Callable]=None
    callbacks:Collection[Callback]=field(default_factory=list)
    layer_groups:Collection[nn.Module]=None
    def __post_init__(self):
        self.path = Path(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.model = self.model.to(self.data.device)
        self.metrics=listify(self.metrics)
        if not self.layer_groups: self.layer_groups = [self.model]
        self.callbacks = listify(self.callbacks)
        self.callback_fns = [Recorder] + listify(self.callback_fns)

    def lr_range(self, lr):
        if not isinstance(lr,slice): return lr
        if lr.start: res = even_mults(lr.start, lr.stop, len(self.layer_groups))
        else: res = [lr.stop/3]*(len(self.layer_groups)-1) + [lr.stop]
        return np.array(res)

    def fit(self, epochs:int, lr:Union[Floats,slice], wd:Floats=None, callbacks:Collection[Callback]=None):
        lr = self.lr_range(lr)
        if wd is None: wd = self.wd
        self.create_opt(lr, wd)
        callbacks = [cb(self) for cb in self.callback_fns] + listify(callbacks)
        fit(epochs, self.model, self.loss_fn, self.opt, self.data, metrics=self.metrics,
            callbacks=self.callbacks+callbacks)

    def create_opt(self, lr:Floats, wd:Floats=0.):
        self.opt = OptimWrapper.create(self.opt_fn, lr, self.layer_groups, wd=wd, true_wd=self.true_wd)

    def split(self, split_on):
        if isinstance(split_on,Callable): split_on = split_on(self.model)
        self.layer_groups = split_model(self.model, split_on)

    def freeze_to(self, n):
        for g in self.layer_groups[:n]:
            for l in g:
                if not self.train_bn or not isinstance(l, bn_types): requires_grad(l, False)
        for g in self.layer_groups[n:]: requires_grad(g, True)

    def freeze(self):
        assert(len(self.layer_groups)>1)
        self.freeze_to(-1)

    def unfreeze(self): self.freeze_to(0)

    def save(self, name): torch.save(self.model.state_dict(), self.path/f'{name}.pth')
    def load(self, name): self.model.load_state_dict(torch.load(self.path/f'{name}.pth'))

def fit_one_cycle(learn:Learner, cyc_len:int, max_lr:float, moms:Tuple[float,float]=(0.95,0.85),
                  div_factor:float=25., pct_start:float=0.5, pct_end:float=0.3, wd:float=0.):
    "Fits a model following the 1cycle policy"
    max_lr = learn.lr_range(max_lr)
    cbs = [OneCycleScheduler(learn, max_lr, moms=moms, div_factor=div_factor,
                             pct_start=pct_start, pct_end=pct_end)]
    learn.fit(cyc_len, max_lr, wd=wd, callbacks=cbs)

Learner.fit_one_cycle = fit_one_cycle
Learner.lr_find = lr_find