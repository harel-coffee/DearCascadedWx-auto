from models.neuralnet import SurvivalNeuralNet
# from models.feedforwardnet import SurvivalFeedForwardNet
from keras.models import Model
from keras.layers import Input, Dense, Dropout
from keras.regularizers import L1L2
import numpy as np
import pandas as pd
import _pickle as cPickle
from keras.utils import to_categorical
from wx_hyperparam import WxHyperParameter
from wx_core import DoFeatureSelectionWX
from sklearn.utils import shuffle
#from lifelines import CoxPHFitter, KaplanMeierFitter
from sklearn.metrics import roc_auc_score
# from sklearn.feature_selection import VarianceThreshold
import os
import models.utils as helper

class SurvivalFFNNCWX(SurvivalNeuralNet):
    def __init__(self, model_name, cancer, omics_type, out_folder, epochs=1000, vecdim=10):
        super(SurvivalFFNNCWX, self).__init__(model_name, cancer, omics_type, out_folder, epochs)
        self.vecdim = vecdim
        self.selected_idx = None
        self.random_seed = 1
        self.cancer_type = cancer
        self.omics_type = omics_type
        self.out_folder = out_folder

    def feature_selection(self, x, c, s, xnames, fold, sel_f_num, dev_index):  
        def get_wx_sel_idx(high_th_year, low_th_year, feature_list, set_feature, sel_feature_num, sel_op, div_ratio = 4):
            high_risk_th = high_th_year*365
            low_risk_th = low_th_year*365
            high_risk_group, low_risk_group = helper.get_risk_group(x,c,s,high_risk_th,low_risk_th)
            trn_x, trn_y, val_x, val_y = helper.get_train_val(high_risk_group, low_risk_group, is_categori_y=True, seed=self.random_seed)
            if len(set_feature):
                trn_x = trn_x[:,set_feature]
                val_x = val_x[:,set_feature]
            feature_num = trn_x.shape[1]

            if sel_feature_num == 0:
                hp = WxHyperParameter(epochs=50, learning_ratio=0.01, batch_size = int(len(trn_x)/4), verbose=True)
                sel_gene_num = int(max(sel_feature_num, feature_num/div_ratio))
            else:
                hp = WxHyperParameter(epochs=50, learning_ratio=0.001, batch_size = int(len(trn_x)/4), verbose=True)
                sel_gene_num = sel_feature_num
            sel_idx, sel_genes, sel_weight, test_auc = DoFeatureSelectionWX(trn_x, trn_y, val_x, val_y, val_x, val_y, feature_list, hp, 
                                                        n_sel=sel_gene_num, sel_option=sel_op)

            return sel_idx

        save_feature_file = self.out_folder+'/FFNNCWX/selected_features_'+self.cancer_type+'_'+self.omics_type+'_'+str(fold)+'.csv'
 
        if os.path.isfile(save_feature_file):
            df = pd.read_csv(save_feature_file)
            sort_index = df['index'].values
            final_sel_idx = sort_index[:sel_f_num]
        else:
            if self.out_folder.split('_')[1] == 'cas':
            # if False:
                if self.omics_type == 'mrna':
                    if self.cancer_type == 'BRCA' or self.cancer_type == 'BLCA':
                        div_ratio = 2
                    else:
                        div_ratio = 4

                step1_sel_idx = get_wx_sel_idx(3,3,xnames,[], 0, 'top', div_ratio = div_ratio)
                step2_sel_idx = get_wx_sel_idx(2,4,step1_sel_idx,step1_sel_idx, 0, 'top', div_ratio = div_ratio)
                sel_f_num_write = len(step2_sel_idx)
                step3_sel_idx = get_wx_sel_idx(1,5,step2_sel_idx,step1_sel_idx[step2_sel_idx], sel_f_num_write, 'top', div_ratio = div_ratio)
                final_sel_idx = step1_sel_idx[step2_sel_idx[step3_sel_idx]]
            else:
                sel_f_num_write = len(xnames)
                final_sel_idx = get_wx_sel_idx(3,3,xnames,[], sel_f_num_write, 'top', div_ratio = 4)

            with open(save_feature_file,'wt') as wFile:
                wFile.writelines("gene,coef,index\n")
                for n,name in enumerate(xnames[final_sel_idx]):
                    wFile.writelines(str(name.split('|')[0])+','+str(sel_f_num_write - n)+','+str(final_sel_idx[n])+'\n')
                    
            final_sel_idx = final_sel_idx[:sel_f_num]

        return final_sel_idx

    def get_model(self, input_size, dropout):
        input_dim = input_size
        # reg = L1L2(l1=1.0, l2=0.5)
        reg = None
        inputs = Input((input_dim,))
        if dropout == 0.0:
            z = inputs#without dropout
        else:
            z = Dropout(dropout)(inputs)
        outputs = Dense(1, kernel_initializer='zeros', bias_initializer='zeros',
                        kernel_regularizer=reg,
                        activity_regularizer=reg,
                        bias_regularizer=reg)(z)
        model = Model(inputs=inputs, outputs=outputs)
        # model.summary()
        return model

    def preprocess_eval(self, x):
        x_new = x[:,self.sel_idx]
        return x_new

    def preprocess(self, x, c, s, xnames, fold, n_sel, dev_index):
        sel_idx = self.feature_selection(x, c, s, xnames, fold, n_sel, dev_index)
        self.sel_idx = sel_idx
        x_new = x[:,sel_idx]
        return x_new