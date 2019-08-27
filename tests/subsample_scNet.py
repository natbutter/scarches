import argparse
import os

import numpy as np
import scanpy as sc

import surgeon


def train_and_evaluate(data_name, freeze=True, count_adata=True):
    path_to_save = f"./results/subsample/{data_name}/"
    condition_key = "batch"
    target_conditions = ["Batch8", "Batch9"]

    os.makedirs(path_to_save, exist_ok=True)

    if count_adata:
        adata = sc.read(f"./data/{data_name}/{data_name}_count.h5ad")
        loss_fn = "nb"
    else:
        adata = sc.read(f"./data/{data_name}/{data_name}_normalized.h5ad")
        loss_fn = "mse"

    adata_out_of_sample = adata[adata.obs[condition_key].isin(target_conditions)]
    adata_for_training = adata[~adata.obs[condition_key].isin(target_conditions)]

    train_adata, valid_adata = surgeon.utils.train_test_split(adata_for_training, 0.85)
    n_conditions = len(train_adata.obs[condition_key].unique().tolist())

    network = surgeon.archs.CVAE(x_dimension=train_adata.shape[1],
                                 z_dimension=20,
                                 n_conditions=n_conditions,
                                 lr=0.001,
                                 alpha=0.001,
                                 eta=1.0,
                                 clip_value=1e6,
                                 loss_fn=loss_fn,
                                 model_path="./models/CVAE/Subsample/Toy_normalized/",
                                 dropout_rate=0.2,
                                 output_activation='relu')

    conditions = adata_for_training.obs[condition_key].unique().tolist()
    condition_encoder = surgeon.utils.create_dictionary(conditions, target_conditions)

    network.train(train_adata,
                  valid_adata,
                  condition_key=condition_key,
                  le=condition_encoder,
                  n_epochs=200,
                  batch_size=128,
                  early_stop_limit=20,
                  lr_reducer=15,
                  n_per_epoch=0,
                  save=True,
                  verbose=2)

    scores = []
    for subsample_frac in [1.0, 0.8, 0.6, 0.4, 0.2]:
        new_network = surgeon.operate(network,
                                      new_conditions=target_conditions,
                                      init='Xavier',
                                      freeze=freeze)
        n_samples = adata_out_of_sample.shape[0]
        keep_idx = np.random.choice(n_samples, int(subsample_frac * n_samples), replace=False)

        adata_out_of_sample = adata_out_of_sample[keep_idx, :]
        train_adata, valid_adata = surgeon.utils.train_test_split(adata_out_of_sample, 0.85)

        new_network.train(train_adata,
                          valid_adata,
                          condition_key=condition_key,
                          le=new_network.condition_encoder,
                          n_epochs=100,
                          batch_size=128,
                          early_stop_limit=25,
                          lr_reducer=20,
                          n_per_epoch=0,
                          save=True,
                          verbose=2)

        encoder_labels, _ = surgeon.utils.label_encoder(
            adata_out_of_sample, label_encoder=network.condition_encoder, condition_key=condition_key)

        latent_adata = new_network.to_latent(adata_out_of_sample, encoder_labels)

        ebm = surgeon.metrics.entropy_batch_mixing(latent_adata, label_key=condition_key, n_pools=1)
        asw = surgeon.metrics.asw(latent_adata, label_key=condition_key)
        ari = surgeon.metrics.ari(latent_adata, label_key=condition_key)
        nmi = surgeon.metrics.nmi(latent_adata, label_key=condition_key)

        scores.append([subsample_frac, ebm, asw, ari, nmi])
        print([subsample_frac, ebm, asw, ari, nmi])

    scores = np.array(scores)

    filename = "scores_"
    filename += "Freezed" if freeze else "UnFreezed"
    filename += "_count.log" if count_adata else "_normalized.log"

    np.savetxt(os.path.join(path_to_save, filename), X=scores, delimiter=",")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='scNet')
    arguments_group = parser.add_argument_group("Parameters")
    arguments_group.add_argument('-d', '--data', type=str, required=True,
                                 help='data name')
    arguments_group.add_argument('-f', '--freeze', type=int, default=1, required=True,
                                 help='freeze')
    arguments_group.add_argument('-c', '--count', type=int, default=0, required=False,
                                 help='latent space dimension')
    args = vars(parser.parse_args())

    data_name = args['data']
    freeze = True if args['freeze'] > 0 else False
    count_adata = True if args['count'] > 0 else False

    train_and_evaluate(data_name=data_name, freeze=freeze, count_adata=count_adata)