import tensorflow as tf

from tensorflow.python.platform import gfile
from tensorflow.python.platform import tf_logging as logging

import DenseNet.nets.densenet as densenet
import DenseNet.preprocessing.densenet_pre as dp

from eval_chest import evaluate
from utils.gen_utils import load_batch, get_dataset, load_batch_dense

import os
import sys
import time
import datetime

slim = tf.contrib.slim

flags = tf.app.flags
flags.DEFINE_float('gpu_p', 1.0, 'Float: allow gpu growth value to pass in config proto')
flags.DEFINE_string('dataset_dir',"data",'String: Your dataset directory')
flags.DEFINE_string('train_dir', "trainlogs", 'String: Your train directory')
flags.DEFINE_boolean('log_device_placement', True,
                            """Whether to log device placement.""")
flags.DEFINE_string('ckpt',"ckpt/tf-densenet121.ckpt",'String: Your dataset directory')
FLAGS = flags.FLAGS

#=======Dataset Informations=======#
dataset_dir = FLAGS.dataset_dir

#Emplacement du checkpoint file
checkpoint_file= FLAGS.ckpt
gpu_p = FLAGS.gpu_p
image_size = 224
#Nombre de classes à prédire
num_class = 15

file_pattern = "chest_%s_*.tfrecord"
file_pattern_for_counting = "chest"
#Création d'un dictionnaire pour reférer à chaque label
labels_to_name = {0:'No Finding', 
                1:'Atelectasis',
                2:'Cardiomegaly', 
                3:'Effusion',
                4: 'Infiltration',
                5: 'Mass',
                6: 'Nodule',
                7: 'Pneumonia',
                8: 'Pneumothorax',
                9: 'Consolidation',
                10: 'Edema',
                11: 'Emphysema',
                12: 'Fibrosis',
                13: 'Pleural_Thickening',
                14: 'Hernia'}
#Create a dictionary that will help people understand your dataset better. This is required by the Dataset class later.

items_to_descriptions = {
    'image': 'A 3-channel RGB coloured flower image that is either... ....',
    'label': 'A label that is as such -- fruits'
}

#=======Training Informations======#
#Nombre d'époques pour l'entraîen
num_epochs = 60

#State your batch size
batch_size = 16

#Learning rate information and configuration (Up to you to experiment)
initial_learning_rate = 0.0001
learning_rate_decay_factor = 0.95
num_epochs_before_decay = 1


def run():
    #Create log_dir:
    if not os.path.exists(FLAGS.train_dir):
        os.mkdir(os.getcwd()+'/'+FLAGS.train_dir)

    #=========== Training ===========#
    #Adding the graph:
    with tf.Graph().as_default() as graph:
        tf.logging.set_verbosity(tf.logging.INFO) #Set the verbosity to INFO level

        dataset = get_dataset("train", dataset_dir, file_pattern=file_pattern, file_pattern_for_counting=file_pattern_for_counting, labels_to_name=labels_to_name)
        images,_, oh_labels, labels = load_batch_dense(dataset, batch_size, image_size, image_size, is_training=True)

        #Calcul of batches/epoch, number of steps after decay learning rate
        num_batches_per_epoch = int(dataset.num_samples / batch_size)
        num_steps_per_epoch = num_batches_per_epoch #Because one step is one batch processed
        decay_steps = int(num_epochs_before_decay * num_steps_per_epoch)

        #Create the model inference
        with slim.arg_scope(densenet.densenet_arg_scope(is_training=True)):
            logits, end_points = densenet.densenet121(images, num_classes = len(labels_to_name), is_training = True)
        
        excluding = ['densenet121/logits','densenet121/Predictions']
        end_points['Predictions']=logits
        end_points['Pred_sig']=tf.nn.sigmoid(logits)
        variable_to_restore = slim.get_variables_to_restore(exclude=excluding)
        logit = tf.squeeze(logits)

        #Defining losses and regulization ops:
        loss = tf.losses.sigmoid_cross_entropy(multi_class_labels = oh_labels, logits = logit)
        total_loss = tf.reduce_mean(tf.losses.get_total_loss())    #obtain the regularization losses as well
        
        #Create the global step for monitoring the learning_rate and training:
        ckpt = tf.train.get_checkpoint_state(FLAGS.train_dir)
        global_step_init = -1
        if ckpt and ckpt.model_checkpoint_path:
            global_step_init = int(ckpt.model_checkpoint_path.split('/')[-1].split('-')[-1])
            global_step = tf.Variable(global_step_init, name='global_step', dtype=tf.int64, trainable=False)

        else:
            global_step = tf.train.get_or_create_global_step()

        lr = tf.train.exponential_decay(learning_rate=initial_learning_rate,
                                        global_step=global_step,
                                        decay_steps=decay_steps,
                                        decay_rate = learning_rate_decay_factor,
                                        staircase=True)
        #State the metrics that you want to predict. We get a predictions that is not one_hot_encoded.
        predictions = tf.argmax(tf.squeeze(end_points['Predictions']),axis=1)
        probabilities = end_points['Pred_sig']
        accuracy = tf.reduce_mean(tf.cast(tf.equal(labels, predictions), tf.float32))

        #Now finally create all the summaries you need to monitor and group them into one summary op.
        tf.summary.scalar('losses/Total_Loss', total_loss)
        tf.summary.scalar('accuracy', accuracy)
        tf.summary.scalar('learning_rate', lr)
        tf.summary.histogram('probabilities', probabilities)
        my_summary_op = tf.summary.merge_all()
        #Define Optimizer with decay learning rate:
        optimizer = tf.train.AdamOptimizer(learning_rate = lr)

        #Create the train_op.
        train_op = optimizer.minimize(total_loss, global_step=global_step)


        

        

        class _LoggerHook(tf.train.SessionRunHook):

            def begin(self):
                self._step = global_step_init
                self.totalloss=0.0
                self.totalacc=0.0

            def before_run(self, run_context):
                self._step += 1
                self._start_time = time.time()
                return tf.train.SessionRunArgs([total_loss, accuracy])  # Asks for loss value.

            def after_run(self, run_context, run_values):
                duration = time.time() - self._start_time
                loss_value, accuracy_value = run_values.results
                if self._step % 1 == 0:
                    num_examples_per_step = batch_size
                    examples_per_sec = num_examples_per_step / duration
                    sec_per_batch = float(duration)
                    self.totalloss += loss_value
                    self.totalacc += accuracy_value
                    format_str = ('\r%s: step %d, avgloss = %.2f, loss = %.2f, avgacc= %.2f ,accuracy=%.2f (%.1f examples/sec; %.3f '
                        'sec/batch)')
                    sys.stdout.write(format_str % (datetime.time(), self._step, self.totalloss/self._step, loss_value, self.totalacc/self._step, accuracy_value,
                               examples_per_sec, sec_per_batch))
                    sys.stdout.flush()

        max_step = num_epochs*num_steps_per_epoch

        saver = tf.train.Saver(variable_to_restore)

        config = tf.ConfigProto()
        config.log_device_placement = True
        config.gpu_options.per_process_gpu_memory_fraction = gpu_p
        #Define your supervisor for running a managed session:
        supervisor = tf.train.MonitoredTrainingSession(checkpoint_dir=FLAGS.train_dir,
                                                        hooks=[tf.train.StopAtStepHook(last_step=max_step),
                                                                tf.train.NanTensorHook(loss),
                                                                _LoggerHook()],
                                                        config=config,
                                                        save_checkpoint_secs=3600,
                                                        save_summaries_steps=20)

        #Running session:
        i=0
        with supervisor as sess:
            ckpt = tf.train.get_checkpoint_state(FLAGS.train_dir)
            if ckpt and ckpt.model_checkpoint_path:
                # Restores from checkpoint
                saver.restore(sess, ckpt.model_checkpoint_path)
            else:
                saver.restore(sess, checkpoint_file)
            while not sess.should_stop():
                if (i+1) % num_steps_per_epoch == 0:
                    ckpt_eval = tf.train.get_checkpoint_state(FLAGS.train_dir)
                    evaluate(ckpt_eval.model_checkpoint_path,
                             dataset_dir,
                             file_pattern,
                             file_pattern_for_counting,
                             labels_to_name,
                             batch_size,
                             image_size,
                            )
                sess.run(train_op)

if __name__ == '__main__':
    run()