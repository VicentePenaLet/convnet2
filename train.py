"""
jsaavedr, 2020

This is a simple version of train.py. 

To use train.py, you will require to set the following parameters :
 * -config : A configuration file where a set of parameters for data construction and training is defined.
 * -name: The section name in the configuration file.
 * -mode: [train, test] for training, testing, or showing  variables of the current model. By default this is set to 'train'
 * -save: Set true for saving the model
"""
import pathlib
import sys
sys.path.append(str(pathlib.Path().absolute()))
import tensorflow as tf
from models import resnet
import datasets.data as data
import utils.imgproc as imgproc
import utils.configuration as conf
import utils.losses as losses
import numpy as np
import argparse
import os

if __name__ == '__main__' :        
    parser = argparse.ArgumentParser(description = "Train a simple mnist model")
    parser.add_argument("-config", type = str, help = "<str> configuration file", required = True)
    parser.add_argument("-name", type=str, help=" name of section in the configuration file", required = True)
    parser.add_argument("-mode", type=str, choices=['train', 'test', 'predict', 'confussion', 'predictImages'],  help=" train, test, predict or confussion", required = False, default = 'train')
    parser.add_argument("-save", type= bool,  help=" True to save the model", required = False, default = False)    
    pargs = parser.parse_args()     
    configuration_file = pargs.config
    configuration = conf.ConfigurationFile(configuration_file, pargs.name)                   
    if pargs.mode == 'train' :
        tfr_train_file = os.path.join(configuration.get_data_dir(), "train.tfrecords")
    if pargs.mode == 'train' or  pargs.mode == 'test' or pargs.mode == "predict" or pargs.mode == "confussion" or pargs.mode == "predictImages":    
        tfr_test_file = os.path.join(configuration.get_data_dir(), "test.tfrecords")
    if configuration.use_multithreads() :
        if pargs.mode == 'train' :
            tfr_train_file=[os.path.join(configuration.get_data_dir(), "train_{}.tfrecords".format(idx)) for idx in range(configuration.get_num_threads())]
        if pargs.mode == 'train' or  pargs.mode == 'test' or pargs.mode == "predict" or pargs.mode == "confussion":    
            tfr_test_file=[os.path.join(configuration.get_data_dir(), "test_{}.tfrecords".format(idx)) for idx in range(configuration.get_num_threads())]        
    sys.stdout.flush()
        
    mean_file = os.path.join(configuration.get_data_dir(), "mean.dat")
    shape_file = os.path.join(configuration.get_data_dir(),"shape.dat")
    #
    input_shape =  np.fromfile(shape_file, dtype=np.int32)
    mean_image = np.fromfile(mean_file, dtype=np.float32)
    mean_image = np.reshape(mean_image, input_shape)
    
    number_of_classes = configuration.get_number_of_classes()
    #loading tfrecords into a dataset object
    if pargs.mode == 'train' : 
        tr_dataset = tf.data.TFRecordDataset(tfr_train_file)        
        tr_dataset = tr_dataset.shuffle(configuration.get_shuffle_size())
        tr_dataset = tr_dataset.map(lambda x : data.parser_tfrecord(x, input_shape, mean_image, number_of_classes, with_augmentation = True));        
        tr_dataset = tr_dataset.batch(batch_size = configuration.get_batch_size())    
        

    if pargs.mode == 'train' or  pargs.mode == 'test':
        val_dataset = tf.data.TFRecordDataset(tfr_test_file)
        val_dataset = val_dataset.map(lambda x : data.parser_tfrecord(x, input_shape, mean_image, number_of_classes, with_augmentation = False));    
        val_dataset = val_dataset.batch(batch_size = configuration.get_batch_size())
                        
    #this code allows program to run in  multiple GPUs. It was tested with 2 gpus.
    #tf.debugging.set_log_device_placement(True)
    #strategy = tf.distribute.MirroredStrategy()
    #with strategy.scope():
    #callback    
    tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=configuration.get_snapshot_dir(), histogram_freq=1)
    #Defining callback for saving checkpoints
    #save_freq: frequency in terms of number steps each time checkpoint is saved 
    model_checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(
        filepath=configuration.get_snapshot_dir() + '{epoch:03d}.h5',
        save_weights_only=True,
        mode = 'max',
        monitor='val_acc',
        save_freq = 'epoch',            
        )
    #save_freq = configuration.get_snapshot_steps())        
    #resnet 34, no bottleneck is required            
    #model = resnet.ResNet([3,4,6,3],[64,128,256,512], configuration.get_number_of_classes(), se_factor = 0)
    #resnet_50
    model = resnet.ResNet([3,4,6,3],[64,128,256,512], configuration.get_number_of_classes(), use_bottleneck = True)
    print('Model is Resnet')
    sys.stdout.flush()    
    #build the model indicating the input shape
    #define the model input
    input_image = tf.keras.Input((input_shape[0], input_shape[1], input_shape[2]), name = 'input_image')     
    model(input_image)    
    model.summary()
    #use_checkpoints to load weights
    if configuration.use_checkpoint() :                
        model.load_weights(configuration.get_checkpoint_file(), by_name = True, skip_mismatch = True)
        #model.load_weights(configuration.get_checkpoint_file(), by_name = False)
    #defining optimizer, my experience shows that SGD + cosine decay is a good starting point        
    #recommended learning_rate is 0.1, and decay_steps = total_number_of_steps                        
    initial_learning_rate= configuration.get_learning_rate()
    lr_schedule = tf.keras.experimental.CosineDecay(initial_learning_rate = initial_learning_rate,
                                                    decay_steps = configuration.get_decay_steps(),
                                                    alpha = 0.0001)

    opt = tf.keras.optimizers.Adam(learning_rate = configuration.get_learning_rate())       
    #opt = tf.keras.optimizers.Adam(learning_rate = configuration.get_learning_rate())
    model.compile(
         optimizer=opt, 
        #optimizer=tf.keras.optimizers.Adam(learning_rate = configuration.get_learning_rate()), # 'adam'     
          loss= losses.crossentropy_loss,
          metrics=['accuracy'])
 
    if pargs.mode == 'train' :                             
        history = model.fit(tr_dataset, 
                        epochs = configuration.get_number_of_epochs(),                        
                        validation_data=val_dataset,
                        validation_steps = configuration.get_validation_steps(),
                        callbacks=[model_checkpoint_callback])
        import matplotlib.pyplot as plt
        print(history.history.keys())
        plt.plot(history.history['accuracy'])
        plt.plot(history.history['val_accuracy'])
        plt.title('model accuracy')
        plt.ylabel('accuracy')
        plt.xlabel('epoch')
        plt.legend(['train', 'val'], loc='upper left')
        plt.savefig('train_graph.svg')

    elif pargs.mode == 'test' :
        model.evaluate(val_dataset,
                       steps = configuration.get_validation_steps(),
                       callbacks=[tensorboard_callback])    

    elif pargs.mode == 'predict':
        filename = input('file :')
        while(filename != 'end') :
            target_size = (configuration.get_image_height(), configuration.get_image_width())
            process_fun = imgproc.process_image
            image = process_fun(data.read_image(filename, configuration.get_number_of_channels()), target_size )
            image = image - mean_image
            image = tf.expand_dims(image, 0)        
            pred = model.predict(image)
            pred = pred[0]
            #softmax to estimate probs
            pred = np.exp(pred - max(pred))
            pred = pred / np.sum(pred)            
            cla = np.argmax(pred)
            print('{} [{}]'.format(cla, pred[cla]))
            filename = input('file :')

    elif pargs.mode == 'confussion':
      from sklearn.metrics import confusion_matrix
      print("Confussion")
      file1 = open('/content/drive/MyDrive/Trees/data/test.txt', 'r')
      Lines = file1.readlines()
      true_label = []
      predicted_label = []
      files = []
      for line in Lines:
        filename = line.strip().split("\t")[0]
        files.append(filename)
        true_label.append(int(line.strip().split("\t")[1]))
        target_size = (configuration.get_image_height(), configuration.get_image_width())
        process_fun = imgproc.process_image
        image = process_fun(data.read_image(filename, configuration.get_number_of_channels()), target_size )
        image = image - mean_image
        image = tf.expand_dims(image, 0)        
        pred = model.predict(image)
        pred = pred[0]
        #softmax to estimate probs
        pred = np.exp(pred - max(pred))
        pred = pred / np.sum(pred)            
        cla = np.argmax(pred)
        predicted_label.append(cla)
        #print('{} [{}]'.format(cla, pred[cla]))
      import pandas as pd
      f = pd.DataFrame(list(zip(true_label, predicted_label)) , columns =['True', 'Predicted'])
      f.to_csv("test_results.csv")
      cfn = confusion_matrix(true_label, predicted_label)
      print(cfn)
      cfn = cfn.astype('float') / cfn.sum(axis=1)[:, np.newaxis]
      import seaborn as sn
      import matplotlib.pyplot as plt
      file1 = open("/content/drive/MyDrive/Trees/data/used_labels.txt", 'r')
      Lines = file1.readlines()
      classes = []
      for line in Lines:
          classes.append(line.strip())
      df_cfm = pd.DataFrame(cfn, index = classes, columns = classes)

      plt.figure(figsize = (10,7))
      cfm_plot = sn.heatmap(df_cfm, annot=True)
      cfm_plot.figure.savefig("cfm.svg")
               
    elif pargs.mode == 'predictImages':
      from IPython.display import Image
      import matplotlib.pyplot as plt
      import matplotlib.image as mpimg
      print("predictImages")
      file1 = open('/content/drive/MyDrive/Trees/data/test.txt', 'r')
      Lines = file1.readlines()
      true_label = []
      predicted_label = []
      files = []
      file1 = open("/content/drive/MyDrive/Trees/data/used_labels.txt", 'r')
      Lines1 = file1.readlines()
      classes = []
      for line in Lines1:
          classes.append(line.strip())
      for line in Lines:
        filename = line.strip().split("\t")[0]
        files.append(filename)
        true_label.append(int(line.strip().split("\t")[1]))
        target_size = (configuration.get_image_height(), configuration.get_image_width())
        process_fun = imgproc.process_image
        image = process_fun(data.read_image(filename, configuration.get_number_of_channels()), target_size )
        image = image - mean_image
        image = tf.expand_dims(image, 0)        
        pred = model.predict(image)
        pred = pred[0]
        #softmax to estimate probs
        pred = np.exp(pred - max(pred))
        pred = pred / np.sum(pred)            
        cla = np.argmax(pred)
        predicted_label.append(cla)
        #print('{} [{}]'.format(cla, pred[cla]))
        tru = int(line.strip().split("\t")[1])
        if tru != cla:
          with open('/content/drive/MyDrive/Trees/data/results', "a") as f:
            f.write(filename + " "+str(tru) +" "+ classes[tru] + " "+str(cla) + " "+classes [cla] +"\n")
    #save the model   
    if pargs.save :
        saved_to = os.path.join(configuration.get_data_dir(),"cnn-model")
        model.save(saved_to)
        print("model saved to {}".format(saved_to))  
