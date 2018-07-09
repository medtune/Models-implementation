import tensorflow as tf

from tensorflow.python.platform import tf_logging as logging

import research.slim.nets.mobilenet_v1 as mobilenet_v1

from utils.gen_utils import load_batch, get_dataset, load_batch_dense

import os
import time
import datetime

slim = tf.contrib.slim


#=======Dataset Informations=======#

main_dir = "./train_fruit"
log_dir= main_dir + "/log_eval"

#=======Training Informations======#
#Nombre d'époques pour l'entraînement
num_epochs = 1

def evaluate(checkpoint_eval, dataset_dir, file_pattern, file_pattern_for_counting, labels_to_name, batch_size, image_size):
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    #Create log_dir:
    with tf.Graph().as_default():
    #=========== Evaluate ===========#
        global_step_cs = tf.train.get_or_create_global_step()
        # Adding the graph:

        dataset = get_dataset("validation", dataset_dir, file_pattern=file_pattern, file_pattern_for_counting=file_pattern_for_counting, labels_to_name=labels_to_name)

        #load_batch_dense is special to densenet or nets that require the same preprocessing
        images,_, oh_labels, labels = load_batch(dataset, batch_size, image_size, image_size, is_training=False)

        #Calcul of batches/epoch, number of steps after decay learning rate
        num_batches_per_epoch = int(dataset.num_samples / batch_size)
        num_steps_per_epoch = num_batches_per_epoch #Because one step is one batch processed


        #Create the model inference
        with slim.arg_scope(mobilenet_v1.mobilenet_v1_arg_scope(is_training=False)):
            net, end_points = mobilenet_v1.mobilenet_v1_050(images, num_classes = None, is_training = False)
        
        kernel_1= tf.get_variable('fcn-1',[1,1,512,256])
        biase_1 = tf.get_variable('biase-1',[1,1,1,256])
        net = tf.add(tf.nn.conv2d(net, kernel_1, [1,1,1,1], padding="VALID", name='Conv2d_1c_1x1'), biase_1)
        end_points['Conv2d_1c_1x1']= net
        kernel_2 = tf.get_variable('fcn-2',[1,1,256,128])
        biase_2 = tf.get_variable('biase-2',[1,1,1,128])
        net = tf.add(tf.nn.conv2d(net, kernel_2, [1,1,1,1], padding="VALID", name='Conv2d_2c_1x1'), biase_2)
        end_points['Conv2d_2c_1x1']= net
        kernel_3 = tf.get_variable('fcn-3',[1,1,128,len(labels_to_name)])
        biase_3 = tf.get_variable('biase-3',[1,1,1,len(labels_to_name)])
        logits = tf.add(tf.nn.conv2d(net, kernel_3, [1,1,1,1], padding="VALID", name='Conv2d_2c_1x1'), biase_3)
        logits = tf.squeeze(logits, [1, 2], name='SpatialSqueeze')
        variables_to_restore = slim.get_variables_to_restore()
        end_points['Predictions_1'] = logits
        #Defining accuracy and predictions:
    
        predictions = tf.argmax(end_points['Predictions_1'], 1)
        probabilities = end_points['Predictions_1']

        #Define the metrics to evaluate
        names_to_values, names_to_updates = slim.metrics.aggregate_metric_map({
        'Accuracy_validation': slim.metrics.streaming_accuracy(predictions, labels),
        })
        for name, value in names_to_values.items():
            summary_name = 'eval/%s' % name
            op = tf.summary.scalar(summary_name, value, collections=[])
            tf.add_to_collection(tf.GraphKeys.SUMMARIES, op)
        #Define and merge summaries:
        tf.summary.histogram('Predictions_validation', probabilities)
        summary_op_val = tf.summary.merge_all()

        #This is the common way to define evaluation using slim
        max_step = num_epochs*num_steps_per_epoch
        initial_op=tf.group(tf.global_variables_initializer(),
                        tf.local_variables_initializer())

        slim.evaluation.evaluate_once(
            master = '',  
            checkpoint_path = checkpoint_eval,
            logdir = log_dir,
            num_evals = max_step,
            initial_op = initial_op,
            eval_op = list(names_to_updates.values()),
            summary_op = summary_op_val,
            variables_to_restore = variables_to_restore)
