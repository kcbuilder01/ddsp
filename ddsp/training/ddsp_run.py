# Copyright 2019 The DDSP Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
r"""Train, evaluate, or sample (from) a ddsp model.

Usage:
================================================================================
For training, you need to specify --gin_file for both the model and the dataset.
You can optionally specify additional params with --gin_param.
The pip install installs a `ddsp_run` script that can be called directly.
================================================================================
ddsp_run \
--mode=train \
--alsologtostderr \
--model_dir=~/tmp/$USER-ddsp-0 \
--gin_file=models/ae.gin \
--gin_file=datasets/nsynth_tfds.gin \
--gin_param=batch_size=16


================================================================================
For evaluation and sampling, only the dataset file is required.
================================================================================
ddsp_run \
--mode=eval \
--alsologtostderr \
--model_dir=~/tmp/$USER-ddsp-0 \
--gin_file=datasets/nsynth_tfds.gin

ddsp_run \
--mode=sample \
--alsologtostderr \
--model_dir=~/tmp/$USER-ddsp-0 \
--gin_file=datasets/nsynth_tfds.gin


================================================================================
The directory `gin/papers/` stores configs that give the specific models and
datasets used for a paper's experiments, so only require one gin file to train.
================================================================================
ddsp_run \
--mode=train \
--alsologtostderr \
--model_dir=~/tmp/$USER-ddsp-0 \
--gin_file=papers/iclr2020/nsynth_ae.gin


"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import time

from absl import app
from absl import flags
from absl import logging
from ddsp.training import eval_util
from ddsp.training import models
from ddsp.training import train_util
import gin
import pkg_resources
import tensorflow.compat.v1 as tf

FLAGS = flags.FLAGS

flags.DEFINE_enum('mode', 'train', ['train', 'eval', 'sample'],
                  'Whether to train, evaluate, or sample from the model.')
flags.DEFINE_string(
    'model_dir', '~/tmp/ddsp',
    'Path where checkpoints and summary events will be located '
    'during training and evaluation.')
flags.DEFINE_string('master', '', 'Name of the TensorFlow runtime to use.')
flags.DEFINE_boolean('use_tpu', False, 'Whether training will happen on a TPU.')

# Gin config flags.
flags.DEFINE_multi_string('gin_search_path', [],
                          'Additional gin file search paths.')
flags.DEFINE_multi_string('gin_file', [], 'List of paths to the config files.')
flags.DEFINE_multi_string('gin_param', [],
                          'Newline separated list of Gin parameter bindings.')

# Training specific flags.
flags.DEFINE_integer('num_train_steps', 1000000,
                     'Number of training steps or `None` for infinite.')

# Evaluation/sampling specific flags.
flags.DEFINE_boolean('eval_once', False, 'Whether evaluation will run once.')
flags.DEFINE_integer('initial_delay_secs', None,
                     'Time to wait before evaluation starts')

GIN_PATH = pkg_resources.resource_filename(__name__, 'gin')


def delay_start():
  """Optionally delay the start of the run."""
  delay_time = FLAGS.initial_delay_secs
  if delay_time:
    logging.info('Waiting for %i second(s)', delay_time)
    time.sleep(delay_time)


def parse_gin(model_dir):
  """Parse gin config from --gin_file, --gin_param, and the model directory."""
  # Add user folders to the gin search path.
  for gin_search_path in [GIN_PATH] + FLAGS.gin_search_path:
    gin.add_config_file_search_path(gin_search_path)

  # Parse gin configs, later calls override earlier ones.
  with gin.unlock_config():
    # Optimization defaults.
    opt_default = 'base_tpu.gin' if FLAGS.use_tpu else 'base.gin'
    gin.parse_config_file(os.path.join('optimization', opt_default))

    # Load operative_config if it exists (model has already trained).
    operative_config = os.path.join(model_dir, 'operative_config-0.gin')
    if tf.gfile.Exists(operative_config):
      gin.parse_config_file(operative_config, skip_unknown=True)

    # Only use the custom cumsum for TPUs.
    gin.parse_config('ddsp.core.cumsum.use_tpu={}'.format(FLAGS.use_tpu))

    # User gin config and user hyperparameters from flags.
    gin.parse_config_files_and_bindings(
        FLAGS.gin_file, FLAGS.gin_param, skip_unknown=True)


def run():
  """Parse gin config and run ddsp training, evaluation, or sampling."""
  model_dir = os.path.expanduser(FLAGS.model_dir)
  parse_gin(model_dir)
  model = models.get_model()

  # Training.
  if FLAGS.mode == 'train':
    train_util.train(
        data_provider=gin.REQUIRED,
        model=model,
        model_dir=model_dir,
        num_steps=FLAGS.num_train_steps,
        master=FLAGS.master,
        use_tpu=FLAGS.use_tpu)

  # Evaluation.
  elif FLAGS.mode == 'eval':
    delay_start()
    eval_util.evaluate(
        data_provider=gin.REQUIRED,
        model=model,
        model_dir=model_dir,
        master=FLAGS.master,
        run_once=FLAGS.eval_once)

  # Sampling.
  elif FLAGS.mode == 'sample':
    delay_start()
    eval_util.sample(
        data_provider=gin.REQUIRED,
        model=model,
        model_dir=model_dir,
        master=FLAGS.master,
        run_once=FLAGS.eval_once)


def main(unused_argv):
  """From command line."""
  run()


def console_entry_point():
  """From pip installed script."""
  tf.disable_v2_behavior()
  app.run(main)


if __name__ == '__main__':
  console_entry_point()
