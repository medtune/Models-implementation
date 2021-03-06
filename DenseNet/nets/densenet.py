import tensorflow as tf

slim = tf.contrib.slim

@slim.add_arg_scope
def _global_avg_pool2d(inputs, scope=None,outputs=None, data_format="NHWC"):
    axis = [1,2] if data_format=="NHWC" else [2,3]
    with tf.variable_scope(scope, 'g_avg', [inputs]) as v_scope:
        net = tf.reduce_mean(inputs, axis=axis,keepdims=True)
        net = slim.utils.collect_named_outputs(outputs, v_scope.name, net)
    return net

@slim.add_arg_scope
def _conv(inputs, number_filters, kernel_size, strides=1, dropout=None, scope=None, outputs=None):
    with tf.variable_scope(scope, 'conv_op', [inputs]) as v_scope:
        net = slim.batch_norm(inputs)
        net = tf.nn.relu(net)
        net = slim.conv2d(net, number_filters, kernel_size)
        if dropout:
            net = tf.nn.dropout(net, keep_prob=dropout)
    return net

@slim.add_arg_scope
def _block(inputs, number_filters, scope=None, outputs=None, data_format='NHWC'):
    with tf.variable_scope(scope, 'conv_blockn', [inputs]) as v_scope:
        net = inputs
        net = _conv(net, number_filters*4, 1, scope="x1")
        net = _conv(net, number_filters,3, scope="x2")
        if data_format=="NHWC":
            net = tf.concat([inputs, net], 3)
        else:
            net = tf.concat([inputs, net], 1)
    return net

@slim.add_arg_scope
def _dense_block(inputs, number_layers, number_filters, growth_rate,
                 grow_num_filters=True, scope=None, outputs=None):

    with tf.variable_scope(scope, 'dense_blockn', [inputs]) as v_scope:
        net = inputs
        for i in range(number_layers):
            branch = i + 1
            net = _block(net, growth_rate, scope='conv_block'+str(branch))
            if grow_num_filters:
                number_filters += growth_rate

    return net, number_filters

@slim.add_arg_scope
def _transition_block(inputs, number_filters, compression=1.0,
                      scope=None, outputs=None):

    num_filters = int(number_filters * compression)
    with tf.variable_scope(scope, 'transition_blockn', [inputs]) as sc:
        net = inputs
        net = _conv(net, num_filters, 1, scope='blk')
        net = slim.avg_pool2d(net, 2)
    return net, num_filters

def densenet(inputs,
             num_classes=1000,
             reduction=None,
             growth_rate=None,
             number_filters=None,
             number_layers=None,
             dropout_rate=0.999,
             is_training=True,
             reuse=None,
             scope=None,
             data_format="NHWC"):
    #Assert conditions 
    assert reduction is not None
    assert growth_rate is not None
    assert number_filters is not None
    assert number_layers is not None

    compression = 1.0 - reduction
    number_dense_blocks = len(number_layers)
    if data_format == 'NCHW':
        inputs = tf.transpose(inputs, [0, 3, 1, 2])
    with tf.variable_scope(scope, 'densenetnnn', [inputs, num_classes],reuse=reuse) as v_scope:
        end_points_collection = v_scope.name + '_end_points'
        net = inputs
        with slim.arg_scope([slim.dropout],
                         is_training=is_training), \
                slim.arg_scope([slim.conv2d, _conv, _block,
                         _dense_block, _transition_block]), \
                                    slim.arg_scope([_conv], dropout=dropout_rate):
            
        # initial convolution
      
            net = slim.conv2d(net, number_filters, 7, stride=2, scope='conv1')
            net = tf.nn.relu(net)
            net = slim.max_pool2d(net, 3, stride=2, padding='SAME')

        # blocks

            for i in range(number_dense_blocks - 1):
                # dense blocks
                net, number_filters = _dense_block(net, number_layers[i], number_filters,
                                        growth_rate,
                                        scope='dense_block' + str(i+1))

                # Add transition_block
                net, number_filters = _transition_block(net, number_filters,
                                             compression=compression,
                                             scope='transition_block' + str(i+1))
            net, num_filters = _dense_block(
                net, number_layers[-1], number_filters,
                growth_rate,
                scope='dense_block' + str(number_dense_blocks))
            # final block
            with tf.variable_scope('final_block', [inputs]):
                net = tf.nn.relu(net)
                net = _global_avg_pool2d(net, scope='global_avg_pool')
            net = slim.conv2d(net, num_classes, 1,
                            biases_initializer=tf.zeros_initializer(),
                            scope='logits')
            end_points = slim.utils.convert_collection_to_dict(end_points_collection)
            net = tf.squeeze(net, axis=[1,2], name="Squeeze")
            if num_classes is not None:
                end_points['Predictions'] = tf.nn.sigmoid(net, name='Predictions')
            return net, end_points


def densenet121(inputs, num_classes=1000, is_training=True, reuse=None, data_format='NHWC'):
    return densenet(inputs,
                    num_classes=num_classes, 
                    reduction=0.5,
                    growth_rate=32,
                    number_filters=64,
                    number_layers=[6,12,24,16],
                    is_training=is_training,
                    reuse=reuse,
                    scope='densenet121')

def densenet161(inputs, num_classes=1000, is_training=True, reuse=None, data_format='NHWC'):
    return densenet(inputs,
                    num_classes=num_classes, 
                    reduction=0.5,
                    growth_rate=48,
                    number_filters=96,
                    number_layers=[6,12,36,24],
                    is_training=is_training,
                    reuse=reuse,
                    scope='densenet161')

def densenet_arg_scope(weight_decay=1e-3,
                       batch_norm_decay=0.99,
                       batch_norm_epsilon=1.1e-5, is_training=True,data_format='NHWC'):

    with slim.arg_scope([slim.conv2d, slim.avg_pool2d, slim.max_pool2d,
                       _block, _global_avg_pool2d], data_format=data_format):

        with slim.arg_scope([slim.conv2d],
                         weights_regularizer=slim.l2_regularizer(weight_decay),
                         activation_fn=None,
                         biases_initializer=None) as scope:
            return scope

