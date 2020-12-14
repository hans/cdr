import math
import pandas as pd

from .kwargs import CDRNNBAYES_INITIALIZATION_KWARGS
from .backend import get_initializer, DenseLayerBayes, CDRNNLayer, CDRNNLayerBayes
from .cdrnnbase import CDRNN
from .util import sn, reg_name, stderr

import tensorflow as tf
from tensorflow.contrib.distributions import Normal, SinhArcsinh

pd.options.mode.chained_assignment = None


class CDRNNBayes(CDRNN):
    _INITIALIZATION_KWARGS = CDRNNBAYES_INITIALIZATION_KWARGS

    _doc_header = """
        A CDRRNN implementation fitted using black box variational Bayes.
    """
    _doc_args = CDRNN._doc_args
    _doc_kwargs = CDRNN._doc_kwargs
    _doc_kwargs += '\n' + '\n'.join([' ' * 8 + ':param %s' % x.key + ': ' + '; '.join([x.dtypes_str(), x.descr]) + ' **Default**: ``%s``.' % (x.default_value if not isinstance(x.default_value, str) else "'%s'" % x.default_value) for x in _INITIALIZATION_KWARGS])
    __doc__ = _doc_header + _doc_args + _doc_kwargs

    ######################################################
    #
    #  Initialization Methods
    #
    ######################################################

    def __init__(self, form_str, X, y, **kwargs):
        super(CDRNNBayes, self).__init__(
            form_str,
            X,
            y,
            **kwargs
        )

        for kwarg in CDRNNBayes._INITIALIZATION_KWARGS:
            setattr(self, kwarg.key, kwargs.pop(kwarg.key, kwarg.default_value))

        self._initialize_metadata()

        self.build()

    def _initialize_metadata(self):
        super(CDRNNBayes, self)._initialize_metadata()

        self.is_bayesian = True

        self.parameter_table_columns = ['Mean', '2.5%', '97.5%']

        if self.intercept_init is None:
            if self.standardize_response:
                self.intercept_init = 0.
            else:
                self.intercept_init = self.y_train_mean
        if self.intercept_prior_sd is None:
            if self.standardize_response:
                self.intercept_prior_sd = self.prior_sd_scaling_coefficient
            else:
                self.intercept_prior_sd = self.y_train_sd * self.prior_sd_scaling_coefficient
        if self.y_sd_prior_sd is None:
            if self.standardize_response:
                self.y_sd_prior_sd = self.y_sd_prior_sd_scaling_coefficient
            else:
                self.y_sd_prior_sd = self.y_train_sd * self.y_sd_prior_sd_scaling_coefficient

        self.kl_penalties = []

        with self.sess.as_default():
            with self.sess.graph.as_default():
                # Define initialization constants
                self.intercept_prior_sd_tf = tf.constant(float(self.intercept_prior_sd), dtype=self.FLOAT_TF)
                self.intercept_posterior_sd_init = self.intercept_prior_sd_tf * self.posterior_to_prior_sd_ratio
                self.intercept_ranef_prior_sd_tf = self.intercept_prior_sd_tf * self.ranef_to_fixef_prior_sd_ratio
                self.intercept_ranef_posterior_sd_init = self.intercept_posterior_sd_init * self.ranef_to_fixef_prior_sd_ratio

                self.y_sd_prior_sd_tf = tf.constant(float(self.y_sd_prior_sd), dtype=self.FLOAT_TF)
                self.y_sd_posterior_sd_init = self.y_sd_prior_sd_tf * self.posterior_to_prior_sd_ratio

                self.y_skewness_prior_sd_tf = tf.constant(float(self.y_skewness_prior_sd), dtype=self.FLOAT_TF)
                self.y_skewness_posterior_sd_init = self.y_skewness_prior_sd_tf * self.posterior_to_prior_sd_ratio

                self.y_tailweight_prior_loc_tf = tf.constant(1., dtype=self.FLOAT_TF)
                self.y_tailweight_posterior_loc_init = tf.constant(1., dtype=self.FLOAT_TF)
                self.y_tailweight_prior_sd_tf = tf.constant(float(self.y_tailweight_prior_sd), dtype=self.FLOAT_TF)
                self.y_tailweight_posterior_sd_init = self.y_tailweight_prior_sd_tf * self.posterior_to_prior_sd_ratio

    def _pack_metadata(self):
        md = super(CDRNNBayes, self)._pack_metadata()
        for kwarg in CDRNNBayes._INITIALIZATION_KWARGS:
            md[kwarg.key] = getattr(self, kwarg.key)

        return md

    def _unpack_metadata(self, md):
        super(CDRNNBayes, self)._unpack_metadata(md)

        for kwarg in CDRNNBayes._INITIALIZATION_KWARGS:
            setattr(self, kwarg.key, md.pop(kwarg.key, kwarg.default_value))

        if len(md) > 0:
            stderr('Saved model contained unrecognized attributes %s which are being ignored\n' %sorted(list(md.keys())))





    ######################################################
    #
    #  Network initialization
    #
    ######################################################


    def _initialize_inputs(self, n_impulse):
        super(CDRNNBayes, self)._initialize_inputs(n_impulse)
        with self.sess.as_default():
            with self.sess.graph.as_default():
                self.use_MAP_mode = tf.placeholder_with_default(tf.logical_not(self.training), shape=[], name='use_MAP_mode')

    def initialize_intercept(self, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                if ran_gf is None:
                    # Posterior distribution
                    intercept_q_loc = tf.Variable(
                        self.intercept_init_tf,
                        name='intercept_q_loc'
                    )

                    intercept_q_scale = tf.Variable(
                        self.constraint_fn_inv(self.intercept_posterior_sd_init),
                        name='intercept_q_scale'
                    )

                    intercept_q_dist = Normal(
                        loc=intercept_q_loc,
                        scale=self.constraint_fn(intercept_q_scale) + self.epsilon,
                        name='intercept_q'
                    )

                    intercept = tf.cond(self.use_MAP_mode, intercept_q_dist.mean, intercept_q_dist.sample)

                    intercept_summary = intercept_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        intercept_prior_dist = Normal(
                            loc=self.intercept_init_tf,
                            scale=self.intercept_prior_sd_tf,
                            name='intercept'
                        )
                        self.kl_penalties.append(intercept_q_dist.kl_divergence(intercept_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    intercept_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels], dtype=self.FLOAT_TF),
                        name='intercept_q_loc_by_%s' % sn(ran_gf)
                    )

                    intercept_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels], dtype=self.FLOAT_TF) * self.constraint_fn_inv(self.intercept_ranef_posterior_sd_init * self.ranef_to_fixef_prior_sd_ratio),
                        name='intercept_q_scale_by_%s' % sn(ran_gf)
                    )

                    intercept_q_dist = Normal(
                        loc=intercept_q_loc,
                        scale=self.constraint_fn(intercept_q_scale) + self.epsilon,
                        name='intercept_q_by_%s' % sn(ran_gf)
                    )

                    intercept = tf.cond(self.use_MAP_mode, intercept_q_dist.mean, intercept_q_dist.sample)

                    intercept_summary = intercept_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        intercept_prior_dist = Normal(
                            loc=0.,
                            scale=self.intercept_prior_sd_tf * self.ranef_to_fixef_prior_sd_ratio,
                            name='intercept_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(intercept_q_dist.kl_divergence(intercept_prior_dist))

                return intercept, intercept_summary

    def initialize_coefficient(self, coef_ids=None, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = len(self.impulse_names) + 1

                coefficient_sd_prior = self.weight_prior_sd
                if isinstance(coefficient_sd_prior, str):
                    if coefficient_sd_prior.lower() in ['xavier', 'glorot']:
                        coefficient_sd_prior = math.sqrt(2 / (units + 1))
                    elif coefficient_sd_prior.lower() == 'he':
                        coefficient_sd_prior = math.sqrt(2 / units)
                else:
                    coefficient_sd_prior = coefficient_sd_prior
                coefficient_sd_posterior = coefficient_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    coefficient_q_loc = tf.Variable(
                        tf.zeros([1, units]),
                        name='coefficient_q_loc'
                    )

                    coefficient_q_scale = tf.Variable(
                        tf.ones([1, units]) * self.constraint_fn_inv(coefficient_sd_posterior),
                        name='coefficient_q_scale'
                    )

                    coefficient_q_dist = Normal(
                        loc=coefficient_q_loc,
                        scale=self.constraint_fn(coefficient_q_scale) + self.epsilon,
                        name='coefficient_q'
                    )

                    coefficient = tf.cond(self.use_MAP_mode, coefficient_q_dist.mean, coefficient_q_dist.sample)

                    coefficient_summary = coefficient_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        coefficient_prior_dist = Normal(
                            loc=0.,
                            scale=coefficient_sd_prior,
                            name='coefficient'
                        )
                        self.kl_penalties.append(coefficient_q_dist.kl_divergence(coefficient_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    coefficient_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='coefficient_q_loc_by_%s' % sn(ran_gf)
                    )

                    coefficient_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(coefficient_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='coefficient_q_scale_by_%s' % sn(ran_gf)
                    )

                    coefficient_q_dist = Normal(
                        loc=coefficient_q_loc,
                        scale=self.constraint_fn(coefficient_q_scale) + self.epsilon,
                        name='coefficient_q_by_%s' % sn(ran_gf)
                    )

                    coefficient = tf.cond(self.use_MAP_mode, coefficient_q_dist.mean, coefficient_q_dist.sample)

                    coefficient_summary = coefficient_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        coefficient_prior_dist = Normal(
                            loc=0.,
                            scale=coefficient_sd_prior * self.ranef_to_fixef_prior_sd_ratio,
                            name='coefficient_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(coefficient_q_dist.kl_divergence(coefficient_prior_dist))

                return coefficient, coefficient_summary

    def initialize_feedforward(
            self,
            units,
            use_bias=True,
            activation=None,
            dropout=None,
            batch_normalization_decay=None,
            name=None
    ):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                projection = DenseLayerBayes(
                    training=self.training,
                    units=units,
                    use_bias=use_bias,
                    activation=activation,
                    dropout=dropout,
                    batch_normalization_decay=batch_normalization_decay,
                    use_MAP_mode=self.use_MAP_mode,
                    kernel_prior_sd=self.weight_prior_sd,
                    bias_prior_sd=self.bias_prior_sd,
                    posterior_to_prior_sd_ratio=self.posterior_to_prior_sd_ratio,
                    constraint=self.constraint,
                    epsilon=self.epsilon,
                    session=self.sess,
                    name=name
                )
                self.kl_penalties += projection.kl_penalties

                return projection

    def initialize_rnn(self, l):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = self.n_units_rnn[l]
                rnn = CDRNNLayerBayes(
                    training=self.training,
                    units=units,
                    time_projection_depth=self.n_layers_irf + 1,
                    activation=self.rnn_activation,
                    recurrent_activation=self.recurrent_activation,
                    time_projection_inner_activation=self.irf_inner_activation,
                    bottomup_dropout=self.input_projection_dropout_rate,
                    h_dropout=self.rnn_h_dropout_rate,
                    c_dropout=self.rnn_c_dropout_rate,
                    forget_rate=self.forget_rate,
                    return_sequences=True,
                    batch_normalization_decay=None,
                    use_MAP_mode=self.use_MAP_mode,
                    kernel_prior_sd=self.weight_prior_sd,
                    bias_prior_sd=self.bias_prior_sd,
                    posterior_to_prior_sd_ratio=self.posterior_to_prior_sd_ratio,
                    constraint=self.constraint,
                    name='rnn_l%d' % (l + 1),
                    epsilon=self.epsilon,
                    session=self.sess
                )
                self.kl_penalties += rnn.kl_penalties

                return rnn

    def initialize_rnn_h(self, l, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = self.n_units_rnn[l]
                
                rnn_h_sd_prior = self.bias_prior_sd
                if isinstance(rnn_h_sd_prior, str):
                    if rnn_h_sd_prior.lower() in ['xavier', 'glorot']:
                        rnn_h_sd_prior = math.sqrt(2 / (units + 1))
                    elif rnn_h_sd_prior.lower() == 'he':
                        rnn_h_sd_prior = math.sqrt(2 / units)
                else:
                    rnn_h_sd_prior = rnn_h_sd_prior
                rnn_h_sd_posterior = rnn_h_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    rnn_h_q_loc = tf.Variable(
                        tf.zeros([1, units]),
                        name='rnn_h_q_loc'
                    )

                    rnn_h_q_scale = tf.Variable(
                        tf.ones([1, units]) * self.constraint_fn_inv(rnn_h_sd_posterior),
                        name='rnn_h_q_scale'
                    )

                    rnn_h_q_dist = Normal(
                        loc=rnn_h_q_loc,
                        scale=self.constraint_fn(rnn_h_q_scale) + self.epsilon,
                        name='rnn_h_q'
                    )

                    rnn_h = tf.cond(self.use_MAP_mode, rnn_h_q_dist.mean, rnn_h_q_dist.sample)

                    rnn_h_summary = rnn_h_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        rnn_h_prior_dist = Normal(
                            loc=0.,
                            scale=rnn_h_sd_prior,
                            name='rnn_h'
                        )
                        self.kl_penalties.append(rnn_h_q_dist.kl_divergence(rnn_h_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    rnn_h_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='rnn_h_q_loc_by_%s' % sn(ran_gf)
                    )

                    rnn_h_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(rnn_h_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='rnn_h_q_scale_by_%s' % sn(ran_gf)
                    )

                    rnn_h_q_dist = Normal(
                        loc=rnn_h_q_loc,
                        scale=self.constraint_fn(rnn_h_q_scale) + self.epsilon,
                        name='rnn_h_q_by_%s' % sn(ran_gf)
                    )

                    rnn_h = tf.cond(self.use_MAP_mode, rnn_h_q_dist.mean, rnn_h_q_dist.sample)

                    rnn_h_summary = rnn_h_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        rnn_h_prior_dist = Normal(
                            loc=0.,
                            scale=rnn_h_sd_prior * self.ranef_to_fixef_prior_sd_ratio,
                            name='rnn_h_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(rnn_h_q_dist.kl_divergence(rnn_h_prior_dist))

                return rnn_h, rnn_h_summary

    def initialize_rnn_c(self, l, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = self.n_units_rnn[l]
                
                rnn_c_sd_prior = self.bias_prior_sd
                if isinstance(rnn_c_sd_prior, str):
                    if rnn_c_sd_prior.lower() in ['xavier', 'glorot']:
                        rnn_c_sd_prior = math.sqrt(2 / (units + 1))
                    elif rnn_c_sd_prior.lower() == 'he':
                        rnn_c_sd_prior = math.sqrt(2 / units)
                else:
                    rnn_c_sd_prior = rnn_c_sd_prior
                rnn_c_sd_posterior = rnn_c_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    rnn_c_q_loc = tf.Variable(
                        tf.zeros([1, units]),
                        name='rnn_c_q_loc'
                    )

                    rnn_c_q_scale = tf.Variable(
                        tf.ones([1, units]) * self.constraint_fn_inv(rnn_c_sd_posterior),
                        name='rnn_c_q_scale'
                    )

                    rnn_c_q_dist = Normal(
                        loc=rnn_c_q_loc,
                        scale=self.constraint_fn(rnn_c_q_scale) + self.epsilon,
                        name='rnn_c_q'
                    )

                    rnn_c = tf.cond(self.use_MAP_mode, rnn_c_q_dist.mean, rnn_c_q_dist.sample)

                    rnn_c_summary = rnn_c_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        rnn_c_prior_dist = Normal(
                            loc=0.,
                            scale=rnn_c_sd_prior,
                            name='rnn_c'
                        )
                        self.kl_penalties.append(rnn_c_q_dist.kl_divergence(rnn_c_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    rnn_c_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='rnn_c_q_loc_by_%s' % sn(ran_gf)
                    )

                    rnn_c_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(rnn_c_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='rnn_c_q_scale_by_%s' % sn(ran_gf)
                    )

                    rnn_c_q_dist = Normal(
                        loc=rnn_c_q_loc,
                        scale=self.constraint_fn(rnn_c_q_scale) + self.epsilon,
                        name='rnn_c_q_by_%s' % sn(ran_gf)
                    )

                    rnn_c = tf.cond(self.use_MAP_mode, rnn_c_q_dist.mean, rnn_c_q_dist.sample)

                    rnn_c_summary = rnn_c_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        rnn_c_prior_dist = Normal(
                            loc=0.,
                            scale=rnn_c_sd_prior * self.ranef_to_fixef_prior_sd_ratio,
                            name='rnn_c_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(rnn_c_q_dist.kl_divergence(rnn_c_prior_dist))

                return rnn_c, rnn_c_summary

    def initialize_h_bias(self, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = self.n_units_hidden_state

                h_bias_sd_prior = self.bias_prior_sd
                if isinstance(h_bias_sd_prior, str):
                    if h_bias_sd_prior.lower() in ['xavier', 'glorot']:
                        h_bias_sd_prior = math.sqrt(2 / (units + 1))
                    elif h_bias_sd_prior.lower() == 'he':
                        h_bias_sd_prior = math.sqrt(2 / units)
                else:
                    h_bias_sd_prior = h_bias_sd_prior
                h_bias_sd_posterior = h_bias_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    h_bias_q_loc = tf.Variable(
                        tf.zeros([1, 1, units]),
                        name='h_bias_q_loc'
                    )

                    h_bias_q_scale = tf.Variable(
                        tf.ones([1, 1, units]) * self.constraint_fn_inv(h_bias_sd_posterior),
                        name='h_bias_q_scale'
                    )

                    h_bias_q_dist = Normal(
                        loc=h_bias_q_loc,
                        scale=self.constraint_fn(h_bias_q_scale) + self.epsilon,
                        name='h_bias_q'
                    )

                    h_bias = tf.cond(self.use_MAP_mode, h_bias_q_dist.mean, h_bias_q_dist.sample)

                    h_bias_summary = h_bias_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        h_bias_prior_dist = Normal(
                            loc=0.,
                            scale=h_bias_sd_prior,
                            name='h_bias'
                        )
                        self.kl_penalties.append(h_bias_q_dist.kl_divergence(h_bias_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    h_bias_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='h_bias_q_loc_by_%s' % sn(ran_gf)
                    )

                    h_bias_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(h_bias_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='h_bias_q_scale_by_%s' % sn(ran_gf)
                    )

                    h_bias_q_dist = Normal(
                        loc=h_bias_q_loc,
                        scale=self.constraint_fn(h_bias_q_scale) + self.epsilon,
                        name='h_bias_q_by_%s' % sn(ran_gf)
                    )

                    h_bias = tf.cond(self.use_MAP_mode, h_bias_q_dist.mean, h_bias_q_dist.sample)

                    h_bias_summary = h_bias_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        h_bias_prior_dist = Normal(
                            loc=0.,
                            scale=h_bias_sd_prior * h_bias_sd_prior,
                            name='h_bias_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(h_bias_q_dist.kl_divergence(h_bias_prior_dist))

                return h_bias, h_bias_summary

    def initialize_irf_l1_biases(self, ran_gf=None):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                units = self.n_units_t_delta_embedding

                irf_l1_W_bias_sd_prior = self.weight_prior_sd
                if isinstance(irf_l1_W_bias_sd_prior, str):
                    if irf_l1_W_bias_sd_prior.lower() in ['xavier', 'glorot']:
                        irf_l1_W_bias_sd_prior = math.sqrt(2 / (units + 1))
                    elif irf_l1_W_bias_sd_prior.lower() == 'he':
                        irf_l1_W_bias_sd_prior = math.sqrt(2 / units)
                else:
                    irf_l1_W_bias_sd_prior = irf_l1_W_bias_sd_prior
                irf_l1_W_bias_sd_posterior = irf_l1_W_bias_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    irf_l1_W_bias_q_loc = tf.Variable(
                        tf.zeros([1, 1, units]),
                        name='irf_l1_W_bias_q_loc'
                    )

                    irf_l1_W_bias_q_scale = tf.Variable(
                        tf.zeros([1, 1, units]) * self.constraint_fn_inv(irf_l1_W_bias_sd_posterior),
                        name='irf_l1_W_bias_q_scale'
                    )

                    irf_l1_W_bias_q_dist = Normal(
                        loc=irf_l1_W_bias_q_loc,
                        scale=self.constraint_fn(irf_l1_W_bias_q_scale) + self.epsilon,
                        name='irf_l1_W_bias_q'
                    )

                    irf_l1_W_bias = tf.cond(self.use_MAP_mode, irf_l1_W_bias_q_dist.mean, irf_l1_W_bias_q_dist.sample)

                    irf_l1_W_bias_summary = irf_l1_W_bias_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        irf_l1_W_bias_prior_dist = Normal(
                            loc=0.,
                            scale=irf_l1_W_bias_sd_prior,
                            name='irf_l1_W_bias'
                        )
                        self.kl_penalties.append(irf_l1_W_bias_q_dist.kl_divergence(irf_l1_W_bias_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    irf_l1_W_bias_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='irf_l1_W_bias_q_loc_by_%s' % sn(ran_gf)
                    )

                    irf_l1_W_bias_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(irf_l1_W_bias_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='irf_l1_W_bias_q_scale_by_%s' % sn(ran_gf)
                    )

                    irf_l1_W_bias_q_dist = Normal(
                        loc=irf_l1_W_bias_q_loc,
                        scale=self.constraint_fn(irf_l1_W_bias_q_scale) + self.epsilon,
                        name='irf_l1_W_bias_q_by_%s' % sn(ran_gf)
                    )

                    irf_l1_W_bias = tf.cond(self.use_MAP_mode, irf_l1_W_bias_q_dist.mean, irf_l1_W_bias_q_dist.sample)

                    irf_l1_W_bias_summary = irf_l1_W_bias_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        irf_l1_W_bias_prior_dist = Normal(
                            loc=0.,
                            scale=irf_l1_W_bias_sd_prior * self.ranef_to_fixef_prior_sd_ratio,
                            name='irf_l1_W_bias_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(irf_l1_W_bias_q_dist.kl_divergence(irf_l1_W_bias_prior_dist))

                irf_l1_b_bias_sd_prior = self.bias_prior_sd
                if isinstance(irf_l1_b_bias_sd_prior, str):
                    if irf_l1_b_bias_sd_prior.lower() in ['xavier', 'glorot']:
                        irf_l1_b_bias_sd_prior = math.sqrt(2 / (units + 1))
                    elif irf_l1_b_bias_sd_prior.lower() == 'he':
                        irf_l1_b_bias_sd_prior = math.sqrt(2 / units)
                else:
                    irf_l1_b_bias_sd_prior = irf_l1_b_bias_sd_prior
                irf_l1_b_bias_sd_posterior = irf_l1_b_bias_sd_prior * self.posterior_to_prior_sd_ratio

                if ran_gf is None:
                    # Posterior distribution
                    irf_l1_b_bias_q_loc = tf.Variable(
                        tf.zeros([1, 1, units]),
                        name='irf_l1_b_bias_q_loc'
                    )

                    irf_l1_b_bias_q_scale = tf.Variable(
                        tf.zeros([1, 1, units]) * self.constraint_fn_inv(irf_l1_b_bias_sd_posterior),
                        name='irf_l1_b_bias_q_scale'
                    )

                    irf_l1_b_bias_q_dist = Normal(
                        loc=irf_l1_b_bias_q_loc,
                        scale=self.constraint_fn(irf_l1_b_bias_q_scale) + self.epsilon,
                        name='irf_l1_b_bias_q'
                    )

                    irf_l1_b_bias = tf.cond(self.use_MAP_mode, irf_l1_b_bias_q_dist.mean, irf_l1_b_bias_q_dist.sample)

                    irf_l1_b_bias_summary = irf_l1_b_bias_q_dist.mean()

                    if self.declare_priors_fixef:
                        # Prior distribution
                        irf_l1_b_bias_prior_dist = Normal(
                            loc=0.,
                            scale=irf_l1_b_bias_sd_prior,
                            name='irf_l1_b_bias'
                        )
                        self.kl_penalties.append(irf_l1_b_bias_q_dist.kl_divergence(irf_l1_b_bias_prior_dist))

                else:
                    rangf_n_levels = self.rangf_n_levels[self.rangf.index(ran_gf)] - 1

                    # Posterior distribution
                    irf_l1_b_bias_q_loc = tf.Variable(
                        tf.zeros([rangf_n_levels, units], dtype=self.FLOAT_TF),
                        name='irf_l1_b_bias_q_loc_by_%s' % sn(ran_gf)
                    )

                    irf_l1_b_bias_q_scale = tf.Variable(
                        tf.ones([rangf_n_levels, units], dtype=self.FLOAT_TF) * self.constraint_fn_inv(irf_l1_b_bias_sd_posterior * self.ranef_to_fixef_prior_sd_ratio),
                        name='irf_l1_b_bias_q_scale_by_%s' % sn(ran_gf)
                    )

                    irf_l1_b_bias_q_dist = Normal(
                        loc=irf_l1_b_bias_q_loc,
                        scale=self.constraint_fn(irf_l1_b_bias_q_scale) + self.epsilon,
                        name='irf_l1_b_bias_q_by_%s' % sn(ran_gf)
                    )

                    irf_l1_b_bias = tf.cond(self.use_MAP_mode, irf_l1_b_bias_q_dist.mean, irf_l1_b_bias_q_dist.sample)

                    irf_l1_b_bias_summary = irf_l1_b_bias_q_dist.mean()

                    if self.declare_priors_ranef:
                        # Prior distribution
                        irf_l1_b_bias_prior_dist = Normal(
                            loc=0.,
                            scale=irf_l1_b_bias_sd_prior * self.ranef_to_fixef_prior_sd_ratio,
                            name='irf_l1_b_bias_by_%s' % sn(ran_gf)
                        )
                        self.kl_penalties.append(irf_l1_b_bias_q_dist.kl_divergence(irf_l1_b_bias_prior_dist))

                return irf_l1_W_bias, irf_l1_W_bias_summary, irf_l1_b_bias, irf_l1_b_bias_summary

    def _initialize_output_model(self):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                if self.y_sd_trainable:
                    y_sd_init_unconstrained = self.y_sd_init_unconstrained

                    # Posterior distribution
                    y_sd_loc_q = tf.Variable(
                        y_sd_init_unconstrained,
                        name='y_sd_loc_q'
                    )
                    y_sd_scale_q = tf.Variable(
                        self.constraint_fn_inv(self.y_sd_posterior_sd_init),
                        name='y_sd_scale_q'
                    )
                    y_sd_dist = Normal(
                        loc=y_sd_loc_q,
                        scale=self.constraint_fn(y_sd_scale_q) + self.epsilon,
                        name='y_sd_q'
                    )

                    y_sd = tf.cond(self.use_MAP_mode, y_sd_dist.mean, y_sd_dist.sample) + self.y_sd_delta

                    y_sd_summary = y_sd_dist.mean() + self.y_sd_delta_ema

                    if self.declare_priors_fixef:
                        # Prior distribution
                        y_sd_prior = Normal(
                            loc=y_sd_init_unconstrained,
                            scale=self.y_sd_prior_sd_tf,
                            name='y_sd'
                        )
                        self.kl_penalties.append(y_sd_dist.kl_divergence(y_sd_prior))

                    y_sd = self.constraint_fn(y_sd) + self.epsilon
                    y_sd_summary = self.constraint_fn(y_sd_summary) + self.epsilon

                    tf.summary.scalar(
                        'error/y_sd',
                        y_sd_summary,
                        collections=['params']
                    )

                else:
                    stderr('Fixed y scale: %s\n' % self.y_sd_init)
                    y_sd = self.y_sd_init_tf
                    y_sd_summary = y_sd

                self.y_sd = y_sd
                self.y_sd_summary = y_sd_summary

                if self.asymmetric_error:
                    # Posterior distributions
                    y_skewness_loc_q = tf.Variable(
                        0.,
                        name='y_skewness_q_loc'
                    )
                    y_skewness_scale_q = tf.Variable(
                        self.constraint_fn_inv(self.y_skewness_posterior_sd_init),
                        name='y_skewness_q_loc'
                    )
                    self.y_skewness_dist = Normal(
                        loc=y_skewness_loc_q,
                        scale=self.constraint_fn(y_skewness_scale_q) + self.epsilon,
                        name='y_skewness_q'
                    )

                    self.y_skewness = tf.cond(self.use_MAP_mode, self.y_skewness_dist.mean, self.y_skewness_dist.sample) + self.y_skewness_delta
                    self.y_skewness_summary = self.y_skewness_dist.mean() + self.y_skewness_delta_ema

                    tf.summary.scalar(
                        'error/y_skewness_summary',
                        self.y_skewness_summary,
                        collections=['params']
                    )

                    y_tailweight_loc_q = tf.Variable(
                        self.constraint_fn_inv(self.y_tailweight_posterior_loc_init),
                        name='y_tailweight_q_loc'
                    )
                    y_tailweight_scale_q = tf.Variable(
                        self.constraint_fn_inv(self.y_tailweight_posterior_sd_init),
                        name='y_tailweight_q_scale'
                    )
                    self.y_tailweight_dist = Normal(
                        loc=y_tailweight_loc_q,
                        scale=self.constraint_fn(y_tailweight_scale_q) + self.epsilon,
                        name='y_tailweight_q'
                    )

                    self.y_tailweight = tf.cond(self.use_MAP_mode, self.y_tailweight_dist.mean, self.y_tailweight_dist.sample) + self.y_tailweight_delta
                    self.y_tailweight_summary = self.y_tailweight_dist.mean() + self.y_tailweight_delta_ema

                    tf.summary.scalar(
                        'error/y_tailweight',
                        self.constraint_fn(self.y_tailweight_summary) + self.epsilon,
                        collections=['params']
                    )

                    if self.declare_priors_fixef:
                        # Prior distributions
                        self.y_skewness_prior = Normal(
                            loc=0.,
                            scale=self.y_skewness_prior_sd_tf,
                            name='y_skewness'
                        )
                        self.y_tailweight_prior = Normal(
                            loc=self.constraint_fn_inv(self.y_tailweight_prior_loc),
                            scale=self.y_tailweight_prior_sd_tf,
                            name='y_tailweight'
                        )
                        self.kl_penalties.append(self.y_skewness_dist.kl_divergence(self.y_skewness_prior))
                        self.kl_penalties.append(self.y_tailweight_dist.kl_divergence(self.y_tailweight_prior))

                    if self.standardize_response:
                        self.out_standardized_dist = SinhArcsinh(
                            loc=self.out,
                            scale=y_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='output_standardized'
                        )
                        self.out_standardized = tf.cond(
                            self.use_MAP_mode,
                            self.out_standardized_dist.mean,
                            self.out_standardized_dist.sample
                        )
                        self.err_dist_standardized_dist = SinhArcsinh(
                            loc=0.,
                            scale=y_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='err_dist_standardized'
                        )
                        self.err_dist_standardized_summary = SinhArcsinh(
                            loc=0.,
                            scale=y_sd_summary,
                            skewness=self.y_skewness_summary,
                            tailweight=self.constraint_fn(self.y_tailweight_summary) + self.epsilon,
                            name='err_dist_standardized_summary'
                        )

                        self.out_dist = SinhArcsinh(
                            loc=self.out * self.y_train_sd + self.y_train_mean,
                            scale=y_sd * self.y_train_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='output_dist'
                        )
                        self.out = tf.cond(
                            self.use_MAP_mode,
                            self.out_dist.mean,
                            self.out_dist.sample
                        )

                        self.err_dist = SinhArcsinh(
                            loc=0.,
                            scale=y_sd * self.y_train_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='err_dist'
                        )
                        self.err = tf.cond(
                            self.use_MAP_mode,
                            self.err_dist.mean,
                            self.err_dist.sample
                        )
                        self.err_dist_summary = SinhArcsinh(
                            loc=0.,
                            scale=y_sd_summary * self.y_train_sd,
                            skewness=self.y_skewness_summary,
                            tailweight=self.constraint_fn(self.y_tailweight_summary) + self.epsilon,
                            name='err_dist_summary'
                        )
                    else:
                        self.out_dist = SinhArcsinh(
                            loc=self.out,
                            scale=y_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='output_dist'
                        )
                        self.out = tf.cond(
                            self.use_MAP_mode,
                            self.out_dist.mean,
                            self.out_dist.sample
                        )

                        self.err_dist = SinhArcsinh(
                            loc=0.,
                            scale=y_sd,
                            skewness=self.y_skewness,
                            tailweight=self.constraint_fn(self.y_tailweight) + self.epsilon,
                            name='err_dist'
                        )
                        self.err = tf.cond(
                            self.use_MAP_mode,
                            self.err_dist.mean,
                            self.err_dist.sample
                        )
                        self.err_dist_summary = SinhArcsinh(
                            loc=0.,
                            scale=y_sd_summary,
                            skewness=self.y_skewness_summary,
                            tailweight=self.constraint_fn(self.y_tailweight_summary) + self.epsilon,
                            name='err_dist_summary'
                        )

                else:
                    if self.standardize_response:
                        self.out_standardized_dist = Normal(
                            loc=self.out,
                            scale=self.y_sd,
                            name='output_standardized'
                        )
                        self.out_standardized = tf.cond(
                            self.use_MAP_mode,
                            self.out_standardized_dist.mean,
                            self.out_standardized_dist.sample
                        )

                        self.err_dist_standardized = Normal(
                            loc=0.,
                            scale=self.y_sd,
                            name='err_dist_standardized'
                        )
                        self.err_standardized = tf.cond(
                            self.use_MAP_mode,
                            self.out_standardized_dist.mean,
                            self.out_standardized_dist.sample
                        )
                        self.err_dist_standardized_summary = Normal(
                            loc=0.,
                            scale=self.y_sd_summary,
                            name='err_dist_standardized_summary'
                        )

                        self.out_dist = Normal(
                            loc=self.out * self.y_train_sd + self.y_train_mean,
                            scale=self.y_sd * self.y_train_sd,
                            name='output'
                        )
                        self.out = tf.cond(
                            self.use_MAP_mode,
                            self.out_dist.mean,
                            self.out_dist.sample
                        )

                        self.err_dist = Normal(
                            loc=0.,
                            scale=self.y_sd * self.y_train_sd,
                            name='err_dist'
                        )
                        self.err = tf.cond(
                            self.use_MAP_mode,
                            self.err_dist.mean,
                            self.err_dist.sample
                        )
                        self.err_dist_summary = Normal(
                            loc=0.,
                            scale=self.y_sd_summary * self.y_train_sd,
                            name='err_dist_summary'
                        )
                    else:
                        self.out_dist = Normal(
                            loc=self.out,
                            scale=self.y_sd,
                            name='output'
                        )
                        self.out = tf.cond(
                            self.use_MAP_mode,
                            self.out_dist.mean,
                            self.out_dist.sample
                        )

                        self.err_dist = Normal(
                            loc=0.,
                            scale=self.y_sd,
                            name='err_dist'
                        )
                        self.err = tf.cond(
                            self.use_MAP_mode,
                            self.err_dist.mean,
                            self.err_dist.sample
                        )
                        self.err_dist_summary = Normal(
                            loc=0.,
                            scale=self.y_sd_summary,
                            name='err_dist_summary'
                        )

                self.err_dist_plot = tf.exp(self.err_dist.log_prob(self.support[None,...]))
                self.err_dist_plot_summary = tf.exp(self.err_dist_summary.log_prob(self.support[None,...]))
                self.err_dist_lb = self.err_dist_summary.quantile(.025)
                self.err_dist_ub = self.err_dist_summary.quantile(.975)

                empirical_quantiles = tf.linspace(0., 1., self.n_errors)
                if self.standardize_response:
                    self.err_dist_standardized_theoretical_quantiles = self.err_dist_standardized.quantile(empirical_quantiles)
                    self.err_dist_standardized_theoretical_cdf = self.err_dist_standardized.cdf(self.errors)
                    self.err_dist_standardized_summary_theoretical_quantiles = self.err_dist_standardized_summary.quantile(empirical_quantiles)
                    self.err_dist_standardized_summary_theoretical_cdf = self.err_dist_standardized_summary.cdf(self.errors)
                self.err_dist_theoretical_quantiles = self.err_dist.quantile(empirical_quantiles)
                self.err_dist_theoretical_cdf = self.err_dist.cdf(self.errors)
                self.err_dist_summary_theoretical_quantiles = self.err_dist_summary.quantile(empirical_quantiles)
                self.err_dist_summary_theoretical_cdf = self.err_dist_summary.cdf(self.errors)

                if self.standardize_response:
                    y_standardized = (self.y - self.y_train_mean) / self.y_train_sd
                    self.ll_standardized = self.out_standardized_dist.log_prob(y_standardized)

    def initialize_objective(self):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                self._initialize_output_model()

                self.loss_func = 0.

                self.ll = self.out_dist.log_prob(self.y)

                self.mae_loss = tf.losses.absolute_difference(self.y, self.out)
                self.mse_loss = tf.losses.mean_squared_error(self.y, self.out)

                loss_func = - self.ll

                if self.loss_filter_n_sds and self.ema_decay:
                    beta = self.ema_decay
                    ema_warm_up = int(2/(1 - self.ema_decay))
                    n_sds = self.loss_filter_n_sds

                    self.loss_ema = tf.Variable(0., trainable=False, name='loss_ema')
                    self.loss_sd_ema = tf.Variable(0., trainable=False, name='loss_sd_ema')

                    loss_cutoff = self.loss_ema + n_sds * self.loss_sd_ema
                    loss_func_filter = tf.cast(loss_func < loss_cutoff, dtype=self.FLOAT_TF)
                    loss_func_filtered = loss_func * loss_func_filter
                    n_batch = tf.cast(tf.shape(loss_func)[0], dtype=self.FLOAT_TF)
                    n_retained = tf.reduce_sum(loss_func_filter)
                    self.n_dropped = n_batch - n_retained

                    loss_func, n_retained = tf.cond(
                        self.global_batch_step > ema_warm_up,
                        lambda loss_func_filtered=loss_func_filtered, n_retained=n_retained: (loss_func_filtered, n_retained),
                        lambda loss_func=loss_func: (loss_func, n_batch),
                    )

                    # loss_func = tf.Print(loss_func, ['cutoff', loss_cutoff, 'n_retained', n_retained, 'ema', self.loss_ema, 'sd ema', self.loss_sd_ema])

                    loss_mean_cur = tf.reduce_sum(loss_func) / (n_retained + self.epsilon)
                    loss_sd_cur = tf.sqrt(tf.reduce_sum((loss_func - self.loss_ema)**2)) / (n_retained + self.epsilon)

                    loss_ema_update = (beta * self.loss_ema + (1 - beta) * loss_mean_cur)
                    loss_sd_ema_update = beta * self.loss_sd_ema + (1 - beta) * loss_sd_cur

                    self.loss_ema_op = tf.assign(self.loss_ema, loss_ema_update)
                    self.loss_sd_ema_op = tf.assign(self.loss_sd_ema, loss_sd_ema_update)

                if self.scale_loss_with_data:
                    self.loss_func = tf.reduce_sum(loss_func) * self.minibatch_scale
                else:
                    self.loss_func = tf.reduce_mean(loss_func)

                for l in self.regularizable_layers:
                    if hasattr(l, 'weights'):
                        vars = l.weights
                    else:
                        vars = [l]
                    for v in vars:
                        if 'bias' not in v.name:
                            self._regularize(v, type='nn', var_name=reg_name(v.name))

                self.reg_loss = tf.constant(0., dtype=self.FLOAT_TF)
                if len(self.regularizer_losses_varnames):
                    self.reg_loss += tf.add_n(self.regularizer_losses)
                    self.loss_func += self.reg_loss

                self.kl_loss = tf.constant(0., dtype=self.FLOAT_TF)
                if len(self.kl_penalties):
                    self.kl_loss += tf.reduce_sum([tf.reduce_sum(x) for x in self.kl_penalties])
                    self.loss_func += self.kl_loss
                    self.reg_loss += self.kl_loss

                assert self.optim_name is not None, 'An optimizer name must be supplied'
                self.optim = self._initialize_optimizer()

                self.train_op = self.optim.minimize(self.loss_func, global_step=self.global_batch_step)




    ######################################################
    #
    #  Public methods
    #
    ######################################################


    def report_settings(self, indent=0):
        out = super(CDRNNBayes, self).report_settings(indent=indent)
        for kwarg in CDRNNBAYES_INITIALIZATION_KWARGS:
            val = getattr(self, kwarg.key)
            out += ' ' * indent + '  %s: %s\n' %(kwarg.key, "\"%s\"" %val if isinstance(val, str) else val)

        out += '\n'

        return out

    def run_train_step(self, feed_dict, verbose=True):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                to_run_names = []
                to_run = [self.train_op, self.ema_op, self.y_sd_delta_ema_op]
                if self.n_layers_rnn:
                    to_run += self.rnn_h_ema_ops + self.rnn_c_ema_ops
                if self.asymmetric_error:
                    to_run += [self.y_skewness_delta_ema_op, self.y_tailweight_delta_ema_op]
                if self.loss_filter_n_sds:
                    to_run_names.append('n_dropped')
                    to_run += [self.loss_ema_op, self.loss_sd_ema_op, self.n_dropped]
                to_run_names += ['loss', 'reg_loss']
                to_run += [self.loss_func, self.reg_loss]
                out = self.sess.run(to_run, feed_dict=feed_dict)

                out_dict = {x: y for x, y in zip(to_run_names, out[-len(to_run_names):])}

                return out_dict

    def run_predict_op(self, feed_dict, standardize_response=False, n_samples=None, algorithm='MAP', verbose=True):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                preds = self.sess.run(self.out, feed_dict=feed_dict)
                if self.standardize_response and not standardize_response:
                    preds = preds * self.y_train_sd + self.y_train_mean
                return preds

    def run_loglik_op(self, feed_dict, standardize_response=False, n_samples=None, algorithm='MAP', verbose=True):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                if self.standardize_response and standardize_response:
                    ll = self.ll_standardized
                else:
                    ll = self.ll
                log_lik = self.sess.run(ll, feed_dict=feed_dict)
                return log_lik

    def run_loss_op(self, feed_dict, n_samples=None, algorithm='MAP', verbose=True):
        with self.sess.as_default():
            with self.sess.graph.as_default():
                loss = self.sess.run(self.loss_func, feed_dict=feed_dict)

                return loss

