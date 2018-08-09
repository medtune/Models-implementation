import tensorflow as tf
slim = tf.contrib.slim
from utils.utils_csv import _get_infos
import research.slim.nets.mobilenet.mobilenet_v2 as mobilenet_v2
from research.slim.preprocessing import inception_preprocessing
import DenseNet.preprocessing.densenet_pre as dp

import pandas as pd
import os
import numpy as np
dataset_dir="D:/MURA-v1.1/"
checkpoint_dir = os.path.join(os.getcwd(),os.path.join("train","training"))
checkpoint_file = os.path.join(checkpoint_dir,"model-56350")

image_size = 224
#Labels 
labels_to_name = {0:'negative', 
                1:'positive'
                }

tf.logging.set_verbosity(tf.logging.INFO)
file_input = tf.placeholder(tf.string, ())
image = tf.image.decode_image(tf.read_file(file_input), channels=3)
image = tf.image.convert_image_dtype(image, tf.float32)
image.set_shape([None,None,3])
image_a = dp.preprocess_image(image, 224,224, is_training=False)
images_bis = tf.expand_dims(image_a,0)
with slim.arg_scope(mobilenet_v2.training_scope(is_training=True)):
    #TODO: Check mobilenet_v1 module, var "excluding
    logits, end_points = mobilenet_v2.mobilenet(images_bis,depth_multiplier=1.4, num_classes = len(labels_to_name))
variables = slim.get_variables_to_restore()
embedding = end_points["layer_18/output"]
pred = tf.argmax(tf.nn.softmax(logits))
one_hot = tf.sparse_to_dense(pred, [len(labels_to_name)], 1.0)
signal = tf.mul(end_points["global_pool"], one_hot)
loss = tf.reduce_mean(signal)
grads = tf.gradients(loss, conv_layer)[0]

print(end_points)