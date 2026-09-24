#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct  7 15:21:55 2018

@author: mishugeb
"""
from scipy.cluster import hierarchy
import matplotlib.pyplot as plt

plt.switch_backend("agg")
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from sklearn import metrics
import time
import multiprocessing
from multiprocessing import current_process
from functools import partial
from numpy import linalg as LA
import sigProfilerPlotting as plot
from sigProfilerPlotting import plotActivity as plot_ac
from sigProfilerPlotting import tmbplot as tmb
import string
import os, sys
import scipy

os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
# import SigProfilerExtractor as cosmic
from scipy.stats import ranksums

# from SigProfilerExtractor import single_sample as ss
from SigProfilerExtractor import nmf_cpu
from sklearn import mixture
from scipy.spatial.distance import cdist
from scipy.spatial.distance import correlation as cor
from scipy.optimize import linear_sum_assignment
from scipy.optimize import nnls

import warnings as _warnings

_warnings.filterwarnings("ignore")
from numpy.random import Generator, PCG64DXSM, SeedSequence


try:
    import torch
    from . import nmf_gpu
except ImportError:
    _warnings.warn("Cannot pytorch - GPU unavailable")

multiprocessing.set_start_method("spawn", force=True)
################################################################## Vivid Functions #############################

############################################################## FUNCTION ONE ##########################################


def make_letter_ids(idlenth=10, mtype="SBS96"):
    listOfSignatures = []
    letters = list(string.ascii_uppercase)
    letters.extend([i + b for i in letters for b in letters])
    letters = letters[0:idlenth]

    for j, l in zip(range(idlenth), letters):
        listOfSignatures.append(mtype + l)
    listOfSignatures = np.array(listOfSignatures)
    return listOfSignatures


def union(a, b):
    """return the union of two lists"""
    return list(set(a) | set(b))


def get_indeces(a, b):
    """
    Extracts the indices multiple items in a list.

    Parameters:
        a: list. where we want to get the index of the items.
        b: list. the items we want to get index of.
    #example:
    x = ['SBS1', 'SBS2', 'SBS3', 'SBS5', 'SBS8', 'SBS13', 'SBS40']
    y = ['SBS1',  'SBS5']
    get_indeces(x, y)
    #result
    >>> [1,3]
    """

    indeces = []
    for i in b:
        try:
            idx = a.index(i)
            indeces.append(idx)
        except:
            next

    return indeces


def get_items_from_index(x, y):
    """decipher the values of items in a list from their indices."""
    z = []
    for i in y:
        try:
            z.append(x[i])
        except:
            pass
    return z


############################################################## FUNCTION ONE ##########################################
def signature_plotting_text(value, text, Type):
    name = text + ": "
    name_list = []
    total = np.sum(np.array(value))
    for i in value:
        if Type == "integer":
            i = int(i)
            p = round(i / total * 100, 1)
            i = format(i, ",d")
            tail = str(i) + "/" + str(p) + "%"
            name_list.append(name + tail)
        elif Type == "float":
            i = round(i, 2)
            name_list.append(name + str(i))
    return name_list


def split_list(lst, splitlenth):
    newlst = []
    for i in range(0, len(lst), splitlenth):
        try:
            newlst.append([lst[i], lst[i + 1]])

        except:
            newlst.append([lst[i]])

    return newlst


############################################ Functions for modifications of Sample Matrices ###############


def get_normalization_cutoff(data, manual_cutoff=9600):
    col_sums = np.array(np.sum(data, axis=0))

    # continue the loop if the differece the means is larger than the 2*2*STD of the larger cluster
    while True:
        try:
            # doing Kmean clustering
            col_sums_for_cluster = col_sums.reshape(-1, 1)

            # separate distributions using mixture model
            clf = mixture.GaussianMixture(n_components=2, covariance_type="full")
            clf.fit(col_sums_for_cluster)
            labels = clf.predict(col_sums_for_cluster)

            unique, counts = np.unique(labels, return_counts=True)
            if len(unique) == 1:
                break
            bigger_cluster = unique[np.argmax(counts)]
            smaller_cluster = unique[np.argmin(counts)]

            # estimating the magnitute of discripancy better the clusters
            bigger_cluster__dist = col_sums[labels == bigger_cluster]
            smaller_cluster__dist = col_sums[labels == smaller_cluster]
            bigger_cluster__dist_mean = np.mean(bigger_cluster__dist)
            bigger_cluster__dist_std = np.std(bigger_cluster__dist)
            smaller_cluster__dist_mean = np.mean(smaller_cluster__dist)
            # continue the loop if the differece the means is larger than the 2*STD of the larger cluster

            if (
                abs(bigger_cluster__dist_mean - smaller_cluster__dist_mean)
                < 2 * 2 * bigger_cluster__dist_std
            ):
                break
            # col_sums will be equal to bigger_cluster__dist for the next iteration
            col_sums = bigger_cluster__dist
        except:
            break

    mean = np.mean(col_sums)
    std = np.std(col_sums)
    cutoff = (mean + 2 * (std)).astype(int)

    if cutoff < manual_cutoff:
        cutoff = manual_cutoff

    return cutoff


def normalize_samples(
    bootstrapGenomes, totalMutations, norm="100X", normalization_cutoff=10000000
):
    """
    Normalization of input data
    """

    if norm == "gmm":
        bootstrapGenomes = np.array(bootstrapGenomes)
        indices = np.where(totalMutations > normalization_cutoff)[0]
        norm_genome = (
            np.array(bootstrapGenomes)[:, list(indices)]
            / np.array(totalMutations)[list(indices)][:, np.newaxis].T
            * normalization_cutoff
        )
        bootstrapGenomes[:, list(indices)] = norm_genome
        bootstrapGenomes = pd.DataFrame(bootstrapGenomes)
    elif norm == "100X":
        bootstrapGenomes = np.array(bootstrapGenomes)
        rows = bootstrapGenomes.shape[0]
        indices = np.where(totalMutations > (rows * 100))[0]
        norm_genome = (
            np.array(bootstrapGenomes)[:, list(indices)]
            / np.array(totalMutations)[list(indices)][:, np.newaxis].T
            * (rows * 100)
        )
        bootstrapGenomes[:, list(indices)] = norm_genome
        bootstrapGenomes = pd.DataFrame(bootstrapGenomes)
    elif norm == "log2":
        log2_of_tM = np.log2(totalMutations)
        bootstrapGenomes = bootstrapGenomes / totalMutations * log2_of_tM
    elif norm == "none":
        pass
    else:
        try:
            bootstrapGenomes = np.array(bootstrapGenomes)
            rows = bootstrapGenomes.shape[0]
            indices = np.where(totalMutations > int(norm))[0]
            norm_genome = (
                np.array(bootstrapGenomes)[:, list(indices)]
                / np.array(totalMutations)[list(indices)][:, np.newaxis].T
                * (int(norm))
            )
            bootstrapGenomes[:, list(indices)] = norm_genome
            bootstrapGenomes = pd.DataFrame(bootstrapGenomes)
        except:
            pass
    return bootstrapGenomes


def split_samples(samples, intervals, rescaled_items, colnames):
    colnames = np.array(colnames)
    total_mutations = samples.sum(axis=0)
    max_total = np.max(total_mutations) + 1
    intervals = np.array(intervals)
    rescaled_items = np.array(rescaled_items)
    (selected_indices,) = np.where(intervals <= max_total)
    intervals = intervals[selected_indices]
    rescaled_items = rescaled_items[selected_indices]
    rescaled_items = list(rescaled_items)

    sample_list = []
    sample_total = []
    rescale_list = []
    rescale_values = []
    colnames_list = []
    ranges = list(intervals) + [max_total]
    for i in range(len(ranges) - 1):
        (sub_sample,) = np.where(
            (total_mutations <= ranges[i + 1]) & (total_mutations > ranges[i])
        )
        if samples[:, sub_sample].shape[1] > 0:
            sample_list.append(samples[:, sub_sample])
            colnames_list.append(list(colnames[sub_sample]))
            sample_total.append(np.sum(samples[:, sub_sample], axis=0))
            rescale_list.append(rescaled_items[i])
            rescale_values.append(ranges[i])
    return (sample_list, colnames_list, sample_total, rescale_list, rescale_values)


def denormalize_samples(genomes, original_totals, normalization_value=30000):
    normalized_totals = np.sum(genomes, axis=0)
    original_totals = np.array(original_totals)
    results = genomes / normalized_totals * original_totals
    results = np.round(results, 0)
    results = results.astype(int)
    return results


def nnmf_cpu(
    genomes, nfactors, init="nndsvd", execution_parameters=None, generator=None
):
    genomes = torch.from_numpy(genomes).float()
    min_iterations = execution_parameters["min_NMF_iterations"]
    max_iterations = execution_parameters["max_NMF_iterations"]
    tolerance = execution_parameters["NMF_tolerance"]
    test_conv = execution_parameters["NMF_test_conv"]
    precision = execution_parameters["precision"]
    net = nmf_cpu.NMF(
        genomes,
        rank=nfactors,
        min_iterations=min_iterations,
        max_iterations=max_iterations,
        tolerance=tolerance,
        test_conv=test_conv,
        init_method=init,
        generator=generator,
        floating_point_precision=precision,
    )
    net.fit()
    Ws = []
    Hs = []

    for H in net.H.detach().cpu().numpy():
        Hs.append(np.matrix(H))
    for W in net.W.detach().cpu().numpy():
        Ws.append(np.matrix(W))

    convergence = int(net.conv)

    W = Ws[0]
    H = Hs[0]
    # calculate L1, L2 and KL for the solution

    est_genome = np.array(np.dot(W, H))
    genomes = np.array(genomes)
    similarities = calculate_similarities(genomes, est_genome, sample_names=False)[
        0
    ].iloc[:, 2:]
    similarities = np.array(np.mean(similarities, axis=0)).T
    similarities = np.append(similarities, convergence)
    return W, H, similarities


def nnmf_gpu(
    genomes, nfactors, init="nndsvd", execution_parameters=None, generator=None
):
    p = current_process()
    identity = p._identity[0]
    gpu_id = identity % torch.cuda.device_count()
    genomes = torch.from_numpy(genomes).float().cuda(gpu_id)
    min_iterations = execution_parameters["min_NMF_iterations"]
    max_iterations = execution_parameters["max_NMF_iterations"]
    tolerance = execution_parameters["NMF_tolerance"]
    test_conv = execution_parameters["NMF_test_conv"]
    precision = execution_parameters["precision"]
    net = nmf_gpu.NMF(
        genomes,
        rank=nfactors,
        min_iterations=min_iterations,
        max_iterations=max_iterations,
        tolerance=tolerance,
        test_conv=test_conv,
        gpu_id=gpu_id,
        init_method=init,
        generator=generator,
        floating_point_precision=precision,
    )
    net.fit()
    Ws = []
    Hs = []
    for H in net.H.detach().cpu().numpy():
        Hs.append(np.matrix(H))
    for W in net.W.detach().cpu().numpy():
        Ws.append(np.matrix(W))

    if len(Ws) == 1:
        convergence = int(net.conv)
    else:
        convergence = int(max_iterations)

    convergence = [convergence] * len(Ws)

    return Ws, Hs, convergence


def BootstrapCancerGenomes(genomes, seed=None):
    """
    index = genomes.index
    cols = genomes.columns
    genomes = np.array(genomes)
    n = 100
    stderr = genomes*0.025
    std = stderr*math.sqrt(n)
    genomes = np.random.normal(genomes, std, size=None).astype(int)
    genomes[genomes<0] = 0

    dataframe = pd.DataFrame(genomes)
    dataframe.index = index
    dataframe.columns = cols
    """

    # normalize the data
    a = pd.DataFrame(
        genomes.sum(0)
    )  # performing the sum of each column. variable a store the sum
    a = (
        a.transpose()
    )  # transfose the value so that if gets a proper dimention to normalize the data
    repmat = pd.concat(
        [a] * genomes.shape[0]
    )  # normalize the data to get the probility of each datapoint to perform the "random.multinomial" operation
    normGenomes = genomes / np.array(repmat)  # part of normalizing step

    # Get the normGenomes as Matlab/ alternation of the "mnrnd" fuction in Matlap
    # do the Boostraping
    dataframe = (
        pd.DataFrame()
    )  # declare an empty variable to populate with the Bootstrapped data
    for i in range(0, normGenomes.shape[1]):
        dataframe[i] = list(
            seed.multinomial(a.iloc[:, i], normGenomes.iloc[:, i], 1)[0]
        )

    return dataframe


# NMF version for the multiprocessing library
def pnmf(
    batch_generator_pair=[1, None],
    genomes=1,
    totalProcesses=1,
    resample=True,
    init="nndsvd",
    normalization_cutoff=10000000,
    norm="log2",
    gpu=False,
    execution_parameters=None,
):
    tic = time.time()
    totalMutations = np.sum(genomes, axis=0)
    genomes = pd.DataFrame(genomes)  # creating/loading a dataframe/matrix

    # generators used for noise and matrix initialization
    poisson_generator = batch_generator_pair[1][0]
    rep_generator = batch_generator_pair[1][1]
    rand_rng = Generator(PCG64DXSM(rep_generator))
    poisson_rng = Generator(PCG64DXSM(poisson_generator))

    precision = execution_parameters["precision"] if execution_parameters else "single"
    np_dtype = np.float32 if precision == "single" else np.float64

    if gpu:
        batch_size = batch_generator_pair[0]
        nmf_fn = nnmf_gpu
        results = []
        genome_list = []

        for b in range(batch_size):
            if resample == True:
                bootstrapGenomes = BootstrapCancerGenomes(genomes, seed=poisson_rng)
            else:
                bootstrapGenomes = genomes

            bootstrapGenomes = bootstrapGenomes.astype(np_dtype)
            bootstrapGenomes[bootstrapGenomes < 0.0001] = 0.0001
            totalMutations = np.sum(bootstrapGenomes, axis=0)
            bootstrapGenomes = normalize_samples(
                bootstrapGenomes,
                totalMutations,
                norm=norm,
                normalization_cutoff=normalization_cutoff,
            )
            genome_list.append(bootstrapGenomes.values)

        g = np.array(genome_list)

        W, H, Conv = nmf_fn(
            g,
            totalProcesses,
            init=init,
            execution_parameters=execution_parameters,
            generator=rand_rng,
        )
        for i in range(len(W)):
            _W = np.array(W[i])
            _H = np.array(H[i])
            total = _W.sum(axis=0, keepdims=True)#[np.newaxis]
            _W = _W / total
            _H = _H * total.T
            _H = denormalize_samples(_H, totalMutations)
            _conv = Conv[i]
            results.append((_W, _H, _conv))
            print("process " + str(totalProcesses) + " continues please wait... ")
            print("execution time: {} seconds \n".format(round(time.time() - tic), 2))
        return results

    else:
        nmf_fn = nnmf_cpu
        if resample == True:
            bootstrapGenomes = BootstrapCancerGenomes(genomes, seed=poisson_rng)
        else:
            bootstrapGenomes = genomes

        bootstrapGenomes = bootstrapGenomes.astype(np_dtype)
        bootstrapGenomes[bootstrapGenomes < 0.0001] = 0.0001

        # normalize the samples to handle the hypermutators

        totalMutations = np.sum(bootstrapGenomes, axis=0)

        bootstrapGenomes = normalize_samples(
            bootstrapGenomes,
            totalMutations,
            norm=norm,
            normalization_cutoff=normalization_cutoff,
        )

        bootstrapGenomes = np.array(bootstrapGenomes)

        W, H, kl = nmf_fn(
            bootstrapGenomes,
            totalProcesses,
            init=init,
            execution_parameters=execution_parameters,
            generator=rand_rng,
        )  # uses custom function nnmf

        W = np.array(W)
        H = np.array(H)
        total = W.sum(axis=0, keepdims=True) #[np.newaxis]
        W = W / total
        H = H * total.T

        # denormalize H
        H = denormalize_samples(H, totalMutations)
        print("process " + str(totalProcesses) + " continues please wait... ")
        print("execution time: {} seconds \n".format(round(time.time() - tic), 2))
        return W, H, kl


def parallel_runs(
    execution_parameters,
    genomes=1,
    totalProcesses=1,
    verbose=False,
    replicate_generators=None,
):
    iterations = execution_parameters["NMF_replicates"]
    init = execution_parameters["NMF_init"]
    normalization_cutoff = execution_parameters["normalization_cutoff"]
    n_cpu = execution_parameters["cpu"]
    resample = execution_parameters["resample"]
    norm = execution_parameters["matrix_normalization"]
    gpu = execution_parameters["gpu"]
    batch_size = execution_parameters["batch_size"]

    if verbose:
        print(
            "Process "
            + str(totalProcesses)
            + " is in progress\n===================================>"
        )
    if n_cpu == -1:
        pool = multiprocessing.Pool()
    else:
        pool = multiprocessing.Pool(processes=n_cpu)

    num_full_batches = iterations // batch_size
    last_batch_size = iterations % batch_size

    # generators used for noise and matrix initialization
    poisson_generator = replicate_generators[0]
    rep_generator = replicate_generators[1]
    # spawn "iterations" number of generators for poisson
    poisson_rand_list = poisson_generator[0].spawn(int(iterations))
    # spawn "iterations" number of generators for W,H
    sub_rand_generators = rep_generator.spawn(int(iterations))
    generator_pair_list = []
    for i, j in zip(poisson_rand_list, sub_rand_generators):
        generator_pair_list.append([i, j])

    batches = [batch_size for _ in range(num_full_batches)]
    if last_batch_size != 0:
        batches.append(last_batch_size)

    batch_generator_pair = []

    # There will be nmf_replicate number of batch_generator_pair elements
    for i, j in zip(batches, generator_pair_list):
        batch_generator_pair.append([i, j])

    if gpu == True:
        # submit jobs for parallel processing
        pool_nmf = partial(
            pnmf,
            genomes=genomes,
            totalProcesses=totalProcesses,
            resample=resample,
            init=init,
            normalization_cutoff=normalization_cutoff,
            norm=norm,
            gpu=gpu,
            execution_parameters=execution_parameters,
        )
        result_list = pool.map(pool_nmf, batch_generator_pair)
        pool.close()
        pool.join()
        flat_list = [item for sublist in result_list for item in sublist]

    else:
        pool_nmf = partial(
            pnmf,
            genomes=genomes,
            totalProcesses=totalProcesses,
            resample=resample,
            init=init,
            normalization_cutoff=normalization_cutoff,
            norm=norm,
            gpu=gpu,
            execution_parameters=execution_parameters,
        )
        result_list = pool.map(pool_nmf, batch_generator_pair)
        pool.close()
        pool.join()
        flat_list = result_list
    return flat_list


#################################### Decipher Signatures ###################################################


def decipher_signatures(
    execution_parameters,
    genomes=[0],
    i=1,
    totalIterations=1,
    cpu=-1,
    mut_context="96",
    noise_rep_pair=None,
):
    # m = mut_context
    tic = time.time()
    # The initial values accumute the results for each number of
    totalMutationTypes = genomes.shape[0]
    totalGenomes = genomes.shape[1]
    totalProcesses = i
    totalIterations = execution_parameters["NMF_replicates"]
    gpu = execution_parameters["gpu"]
    dist = execution_parameters["dist"]
    norm = execution_parameters["matrix_normalization"]
    normalization_cutoff = execution_parameters["normalization_cutoff"]

    # poisson_generator is index 0, and random_generator is index 1
    replicate_generators = noise_rep_pair[:2]
    cluster_rand_seq = noise_rep_pair[2]
    print(
        "Extracting signature {} for mutation type {}".format(
            totalProcesses, mut_context
        )
    )  # m is for the mutation context

    if norm == "gmm":
        print("The matrix normalizing cutoff is {}\n\n".format(normalization_cutoff))
    else:
        print("The matrix normalizing cutoff is set for {}\n\n".format(norm))

    ##############################################################################################################################################################################
    ############################################################# The parallel processing takes place here #######################################################################
    ##############################################################################################################################################################################
    if gpu == True:
        results = []
        flat_list = parallel_runs(
            execution_parameters,
            genomes=genomes,
            totalProcesses=totalProcesses,
            verbose=False,
            replicate_generators=replicate_generators,
        )

        for items in range(len(flat_list)):
            W = flat_list[items][0]
            H = flat_list[items][1]
            conv = flat_list[items][2]
            # calculate L1, L2 and KL for the solution
            est_genome = np.array(np.dot(W, H))

            similarities = calculate_similarities(
                genomes, est_genome, sample_names=False
            )[0].iloc[:, 2:]
            similarities = np.array(np.mean(similarities, axis=0)).T
            similarities = np.append(similarities, conv)

            results.append([W, H, similarities])
    else:
        results = parallel_runs(
            execution_parameters,
            genomes=genomes,
            totalProcesses=totalProcesses,
            verbose=False,
            replicate_generators=replicate_generators,
        )
    toc = time.time()
    print(
        "Time taken to collect {} iterations for {} signatures is {} seconds".format(
            totalIterations, totalProcesses, round(toc - tic, 2)
        )
    )
    ##############################################################################################################################################################################
    ######################################################### The parallel processing ends here ##################################################################################
    ##############################################################################################################################################################################

    ################### Achieve the best clustering by shuffling results list using a few iterations ##########
    Wall = np.zeros((totalMutationTypes, totalProcesses * totalIterations))
    Hall = np.zeros((totalProcesses * totalIterations, totalGenomes))
    converge_information = np.zeros((totalIterations, 7))

    finalgenomeErrors = np.zeros((totalMutationTypes, totalGenomes, totalIterations))
    finalgenomesReconstructed = np.zeros(
        (totalMutationTypes, totalGenomes, totalIterations)
    )

    processCount = 0
    for j in range(len(results)):
        W = results[j][0]
        H = results[j][1]
        if not (np.isfinite(W).all() and np.isfinite(H).all()):
            raise FloatingPointError(
                "NMF replicate {} of {} at rank {} returned non-finite values "
                "(NaN or inf) in W or H.".format(j + 1, len(results), totalProcesses)
            )
        converge_information[j, :] = results[j][2][:]
        finalgenomeErrors[:, :, j] = genomes - np.dot(W, H)
        finalgenomesReconstructed[:, :, j] = np.dot(W, H)
        Wall[:, processCount : (processCount + totalProcesses)] = W
        Hall[processCount : (processCount + totalProcesses), :] = H
        processCount = processCount + totalProcesses

    processes = i  # renamed the i as "processes"
    (
        processAvg,
        exposureAvg,
        processSTE,
        exposureSTE,
        avgSilhouetteCoefficients,
        clusterSilhouetteCoefficients,
    ) = cluster_converge_outerloop(
        Wall,
        Hall,
        processes,
        dist=dist,
        gpu=gpu,
        cluster_rand_seq=cluster_rand_seq,
        n_cpu=execution_parameters["cpu"],
    )
    reconstruction_error = round(
        LA.norm(genomes - np.dot(processAvg, exposureAvg), "fro")
        / LA.norm(genomes, "fro"),
        2,
    )

    return (
        processAvg,
        exposureAvg,
        processSTE,
        exposureSTE,
        avgSilhouetteCoefficients,
        np.round(clusterSilhouetteCoefficients, 3),
        finalgenomeErrors,
        finalgenomesReconstructed,
        Wall,
        Hall,
        converge_information,
        reconstruction_error,
        processes,
    )


############################################################### FUNCTIONS TO CALCULATE DISTANCES BETWEEN VECTORS ##################################################
################################################################### FUNCTION ONE ###################################################################
# function to calculate the cosine similarity
def cos_sim(a, b):
    """Takes 2 vectors a, b and returns the cosine similarity according
    to the definition of the dot product

    Dependencies:
    *Requires numpy library.
    *Does not require any custom function (constructed by me)

    Required by:
    * pairwise_cluster_raw
    """
    if np.sum(a) == 0 or np.sum(b) == 0:
        return 0.0
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    return dot_product / (norm_a * norm_b)


def cor_sim(a, b):
    """Takes 2 vectors a, b and returns the corrilation similarity according
    to the definition of the dot product

    Dependencies:
    *Requires numpy library.
    *Does not require any custom function (constructed by me)

    Required by:
    * pairwise_cluster_raw
    """
    if np.sum(a) == 0 or np.sum(b) == 0:
        return 0.0
    corr = 1 - cor(a, b)
    return corr


################################################################### FUNCTION ONE ###################################################################
# function to calculate multiple similarities/distances
def calculate_similarities(genomes, est_genomes, sample_names=False):
    from numpy import inf

    if sample_names is False:
        sample_names = ["None"] * genomes.shape[1]

    cosine_similarity_list = []
    kl_divergence_list = []
    correlation_list = []
    l1_norm_list = []
    l2_norm_list = []
    total_mutations_list = []
    relative_l1_list = []
    relative_l2_list = []

    for i in range(genomes.shape[1]):
        p_i = genomes[:, i]
        q_i = est_genomes[:, i]
        cosine_similarity_list.append(round(cos_sim(p_i, q_i), 3))
        kl_divergence_list.append(round(scipy.stats.entropy(p_i, q_i), 5))
        correlation_list.append(round(scipy.stats.pearsonr(p_i, q_i)[0], 3))
        l1_norm_list.append(round(np.linalg.norm(p_i - q_i, ord=1), 3))
        relative_l1_list.append(
            round((l1_norm_list[-1] / np.linalg.norm(p_i, ord=1)) * 100, 3)
        )
        l2_norm_list.append(round(np.linalg.norm(p_i - q_i, ord=2), 3))
        relative_l2_list.append(
            round((l2_norm_list[-1] / np.linalg.norm(p_i, ord=2)) * 100, 3)
        )
        total_mutations_list.append(np.sum(p_i))

    kl_divergence_list = np.array(kl_divergence_list)
    kl_divergence_list[kl_divergence_list == inf] = 1000
    similarities_dataframe = pd.DataFrame(
        {
            "Sample Names": sample_names,
            "Total Mutations": total_mutations_list,
            "Cosine Similarity": cosine_similarity_list,
            "L1 Norm": l1_norm_list,
            "L1_Norm_%": relative_l1_list,
            "L2 Norm": l2_norm_list,
            "L2_Norm_%": relative_l2_list,
            "KL Divergence": kl_divergence_list,
            "Correlation": correlation_list,
        }
    )
    similarities_dataframe = similarities_dataframe.set_index("Sample Names")
    return [similarities_dataframe, cosine_similarity_list]


################################################################ CLUSTERING FUNCTIONS ################################################################
################################################################### FUNCTION ONE ###################################################################
# function to calculate the centroids


################################################################### FUNCTION  ###################################################################
def pairwise_cluster_raw(
    mat1=([0]), mat2=([0]), dist="cosine"
):  # the matrices (mat1 and mat2) are used to calculate the clusters and the lsts will be used to store the members of clusters
    """Takes a pair of matrices mat1 and mat2 as arguments. Both of the matrices should have the
    equal shapes. The function makes a partition based clustering (the number of clusters is equal
    to the number of colums of the matrices, and not more column is assigned into a cluster from
    a single matrix). It return the list of clusters  as "lstCluster" and the list of clusters
    based on their indeces of the vectors in their original matrices. Please run the
    test of function/example code provided below the for better understanding.

     Dependencies:
        *cos_sim

    Required by:
        *pairwise_cluster_init
        *pairwise_cluster_elong


    """

    if dist == "cosine":
        con_mat = cdist(mat1.T, mat2.T, "cosine")
    elif dist == "correlation":
        con_mat = cdist(mat1.T, mat2.T, "correlation")

    row_ind, col_ind = linear_sum_assignment(con_mat)

    idxPair = []
    for i, j in zip(row_ind, col_ind):
        idxPair.append([i, j])

    return idxPair


################################################################### FUNCTION  ###################################################################
def reclustering(
    tempWall=0, tempHall=0, processAvg=0, exposureAvg=0, dist="cosine", gpu=False
):
    # exposureAvg is not important here. It can be any matrix with the same size of a single exposure matrix
    iterations = int(tempWall.shape[1] / processAvg.shape[1])
    processes = processAvg.shape[1]
    idxIter = list(range(0, tempWall.shape[1], processes))

    processes3D = np.zeros([processAvg.shape[1], processAvg.shape[0], iterations])
    exposure3D = np.zeros([exposureAvg.shape[0], iterations, exposureAvg.shape[1]])

    for iteration_number in range(len(idxIter)):
        statidx = idxIter[iteration_number]
        loopidx = list(range(statidx, statidx + processes))
        idxPair = pairwise_cluster_raw(
            mat1=processAvg, mat2=tempWall[:, loopidx], dist=dist
        )

        for cluster_items in idxPair:
            cluster_number = cluster_items[0]
            query_idx = cluster_items[1]
            processes3D[cluster_number, :, iteration_number] = tempWall[
                :, statidx + query_idx
            ]
            exposure3D[cluster_number, iteration_number, :] = tempHall[
                statidx + query_idx, :
            ]

    count = 0
    labels = []
    clusters_list = []  # Use a list to collect DataFrames

    for cluster_id in range(processes3D.shape[0]):
        cluster_vectors = pd.DataFrame(processes3D[cluster_id, :, :])
        clusters_list.append(cluster_vectors.T)  # Collect DataFrames into a list
        for k in range(cluster_vectors.shape[1]):
            labels.append(count)
        count = count + 1

    # Concatenate all DataFrames at once
    clusters = pd.concat(clusters_list, ignore_index=True)
    try:
        if dist == "cosine":
            SilhouetteCoefficients = metrics.silhouette_samples(
                clusters, labels, metric="cosine"
            )
        if dist == "correlation":
            SilhouetteCoefficients = metrics.silhouette_samples(
                clusters, labels, metric="correlation"
            )

    except:
        SilhouetteCoefficients = np.ones((len(labels), 1))

    avgSilhouetteCoefficients = np.mean(SilhouetteCoefficients)

    # clusterSilhouetteCoefficients
    splitByCluster = np.array_split(SilhouetteCoefficients, processes3D.shape[0])
    clusterSilhouetteCoefficients = np.array([])
    for i in splitByCluster:
        clusterSilhouetteCoefficients = np.append(
            clusterSilhouetteCoefficients, np.mean(i)
        )

    processAvg = np.mean(processes3D, axis=2).T
    processSTE = scipy.stats.sem(processes3D, axis=2, ddof=1).T
    exposureAvg = np.mean(exposure3D, axis=1)
    exposureSTE = scipy.stats.sem(exposure3D, axis=1, ddof=1)

    return (
        processAvg,
        exposureAvg,
        processSTE,
        exposureSTE,
        avgSilhouetteCoefficients,
        clusterSilhouetteCoefficients,
    )


def cluster_converge_innerloop(
    Wall,
    Hall,
    totalprocess,
    iteration_generator_pair,
    iteration=1,
    dist="cosine",
    gpu=False,
):
    rng_generator = Generator(PCG64DXSM(iteration_generator_pair[1]))
    processAvg = rng_generator.random((Wall.shape[0], totalprocess))
    exposureAvg = rng_generator.random((totalprocess, Hall.shape[1]))

    result = 0
    convergence_count = 0
    while True:
        (
            processAvg,
            exposureAvg,
            processSTE,
            exposureSTE,
            avgSilhouetteCoefficients,
            clusterSilhouetteCoefficients,
        ) = reclustering(Wall, Hall, processAvg, exposureAvg, dist=dist, gpu=gpu)

        if result == avgSilhouetteCoefficients:
            break
        elif convergence_count == 10:
            break
        else:
            result = avgSilhouetteCoefficients
            convergence_count = convergence_count + 1

    return (
        processAvg,
        exposureAvg,
        processSTE,
        exposureSTE,
        avgSilhouetteCoefficients,
        clusterSilhouetteCoefficients,
    )


def parallel_clustering(
    Wall,
    Hall,
    totalProcesses,
    iterations=50,
    n_cpu=-1,
    dist="cosine",
    gpu=False,
    cluster_rand_seq=None,
):
    if n_cpu == -1:
        pool = multiprocessing.Pool()
    else:
        pool = multiprocessing.Pool(processes=n_cpu)

    # create random generators for each subprocess
    sub_rand_generator = cluster_rand_seq.spawn(iterations)
    iteration_generator_pairs = []
    # pair generator with an interation
    for i, j in zip(range(iterations), sub_rand_generator):
        iteration_generator_pairs.append([i, j])

    pool_nmf = partial(
        cluster_converge_innerloop, Wall, Hall, totalProcesses, dist=dist, gpu=gpu
    )
    result_list = pool.map(pool_nmf, iteration_generator_pairs)
    pool.close()
    pool.join()
    return result_list


# To select the best clustering converge of the cluster_converge_innerloop
def cluster_converge_outerloop(
    Wall, Hall, totalprocess, dist="cosine", gpu=False, cluster_rand_seq=None, n_cpu=-1
):
    avgSilhouetteCoefficients = -1  # intial avgSilhouetteCoefficients

    # do the parallel clustering
    result_list = parallel_clustering(
        Wall,
        Hall,
        totalprocess,
        iterations=50,
        n_cpu=n_cpu,
        dist=dist,
        gpu=gpu,
        cluster_rand_seq=cluster_rand_seq,
    )

    for i in range(50):  # using 10 iterations to get the best clustering
        (
            temp_processAvg,
            temp_exposureAvg,
            temp_processSTE,
            temp_exposureSTE,
            temp_avgSilhouetteCoefficients,
            temp_clusterSilhouetteCoefficients,
        ) = (
            result_list[i][0],
            result_list[i][1],
            result_list[i][2],
            result_list[i][3],
            result_list[i][4],
            result_list[i][5],
        )

        if avgSilhouetteCoefficients < temp_avgSilhouetteCoefficients:
            (
                processAvg,
                exposureAvg,
                processSTE,
                exposureSTE,
                avgSilhouetteCoefficients,
                clusterSilhouetteCoefficients,
            ) = (
                temp_processAvg,
                temp_exposureAvg,
                temp_processSTE,
                temp_exposureSTE,
                temp_avgSilhouetteCoefficients,
                temp_clusterSilhouetteCoefficients,
            )

    return (
        processAvg,
        exposureAvg,
        processSTE,
        exposureSTE,
        avgSilhouetteCoefficients,
        clusterSilhouetteCoefficients,
    )


################################################### Generation of probabilities for each processes given to A mutation type ############################################
def probabilities(W, H, index, allsigids, allcolnames):
    # setting up the indices
    rows = index
    cols = allcolnames
    sigs = allsigids

    W = np.array(W)
    H = np.array(H)
    # rebuild the original matrix from the estimated W and H
    genomes = np.dot(W, H)

    result = 0
    for i in range(H.shape[1]):  # here H.shape is the number of sample
        M = np.array(genomes)[:, i][np.newaxis]
        probs = W * H[:, i] / M.T
        probs = pd.DataFrame(probs)
        probs.columns = sigs
        col1 = [cols[i]] * len(rows)
        probs.insert(loc=0, column="Sample Names", value=col1)
        probs.insert(loc=1, column="MutationType", value=rows)
        if i != 0:
            result = pd.concat([result, probs], axis=0)
        else:
            result = probs

    return result


##########################################################################################################################################################################
#################################################################### Data loading and Result Exporting  ###################################################################################
##########################################################################################################################################################################

########################################################### Functions to load the MATLAB OBJECTS ###################


def extract_arrays(data, field, index=True):
    accumulator = list()
    if index == False:
        for i in data[field]:
            accumulator.append(i)
        return accumulator
    else:
        for i in data[field]:
            accumulator.append(i[0][0])
        return accumulator


def extract_input(data):
    originalGenome = data["originalGenomes"]
    cancerType = extract_arrays(data, "cancerType", False)
    sampleNames = extract_arrays(data, "sampleNames", True)
    subTypes = extract_arrays(data, "subtypes", True)
    types = extract_arrays(data, "types", True)
    allFields = [cancerType, originalGenome, sampleNames, subTypes, types]
    return allFields


##################################### Get Input From CSV Files ##############################################


def read_csv(filename, folder=False):
    if folder == False:
        if type(filename) == str:
            genomes = pd.read_csv(filename, sep=",").iloc[:, :]
        else:
            genomes = filename
    else:
        count = 1
        for file in os.listdir(filename):
            # print(count)
            df = pd.read_csv(filename + "/" + file)
            if count == 1:
                genomes = df
            else:
                genomes = pd.merge(genomes, df, on=["Mutation type", "Trinucleotide"])
            count += 1
    mtypes = [str(genomes.shape[0])]

    if mtypes == ["96"]:
        # create the list to sort the mutation types
        orderlist = [
            "A[C>A]A",
            "A[C>A]C",
            "A[C>A]G",
            "A[C>A]T",
            "A[C>G]A",
            "A[C>G]C",
            "A[C>G]G",
            "A[C>G]T",
            "A[C>T]A",
            "A[C>T]C",
            "A[C>T]G",
            "A[C>T]T",
            "A[T>A]A",
            "A[T>A]C",
            "A[T>A]G",
            "A[T>A]T",
            "A[T>C]A",
            "A[T>C]C",
            "A[T>C]G",
            "A[T>C]T",
            "A[T>G]A",
            "A[T>G]C",
            "A[T>G]G",
            "A[T>G]T",
            "C[C>A]A",
            "C[C>A]C",
            "C[C>A]G",
            "C[C>A]T",
            "C[C>G]A",
            "C[C>G]C",
            "C[C>G]G",
            "C[C>G]T",
            "C[C>T]A",
            "C[C>T]C",
            "C[C>T]G",
            "C[C>T]T",
            "C[T>A]A",
            "C[T>A]C",
            "C[T>A]G",
            "C[T>A]T",
            "C[T>C]A",
            "C[T>C]C",
            "C[T>C]G",
            "C[T>C]T",
            "C[T>G]A",
            "C[T>G]C",
            "C[T>G]G",
            "C[T>G]T",
            "G[C>A]A",
            "G[C>A]C",
            "G[C>A]G",
            "G[C>A]T",
            "G[C>G]A",
            "G[C>G]C",
            "G[C>G]G",
            "G[C>G]T",
            "G[C>T]A",
            "G[C>T]C",
            "G[C>T]G",
            "G[C>T]T",
            "G[T>A]A",
            "G[T>A]C",
            "G[T>A]G",
            "G[T>A]T",
            "G[T>C]A",
            "G[T>C]C",
            "G[T>C]G",
            "G[T>C]T",
            "G[T>G]A",
            "G[T>G]C",
            "G[T>G]G",
            "G[T>G]T",
            "T[C>A]A",
            "T[C>A]C",
            "T[C>A]G",
            "T[C>A]T",
            "T[C>G]A",
            "T[C>G]C",
            "T[C>G]G",
            "T[C>G]T",
            "T[C>T]A",
            "T[C>T]C",
            "T[C>T]G",
            "T[C>T]T",
            "T[T>A]A",
            "T[T>A]C",
            "T[T>A]G",
            "T[T>A]T",
            "T[T>C]A",
            "T[T>C]C",
            "T[T>C]G",
            "T[T>C]T",
            "T[T>G]A",
            "T[T>G]C",
            "T[T>G]G",
            "T[T>G]T",
        ]
        # Contruct the indeces of the matrix
        # setting index and columns names of processAvg and exposureAvg
        index1 = genomes.iloc[:, 1]
        index2 = genomes.iloc[:, 0]
        index = []
        for i, j in zip(index1, index2):
            index.append(i[0] + "[" + j + "]" + i[2])

        index = np.array(pd.Series(index))
        genomes["index"] = index

        # sort the mutationa types
        genomes["index"] = pd.Categorical(genomes["index"], orderlist)
        genomes = genomes.sort_values("index")

        genomes = genomes.iloc[:, 2 : genomes.shape[1]]

        # set the index
        genomes = genomes.set_index("index")

        # prepare the index and colnames variables
        index = np.array(orderlist)
        colnames = np.array(pd.Series(genomes.columns.tolist()))

    else:
        index = np.array(genomes.iloc[:, 0])
        genomes = genomes.iloc[:, 1:]
        genomes = genomes.loc[:, (genomes != 0).any(axis=0)]
        colnames = genomes.columns

    return (genomes, index, colnames, mtypes)


###################################################################################### Export Results ###########################################
def export_information(
    loopResults,
    mutation_type,
    output,
    index,
    colnames,
    sequence="genome",
    wall=False,
    volume=None,
):
    # get the number of processes
    i = loopResults[-1]
    # get Wall and Hall
    Wall = loopResults[-3]
    Hall = loopResults[-2]

    # get the mutational contexts
    # print ("The mutaion type is", mutation_type)
    m = mutation_type
    # Create the neccessary directories
    subdirectory = (
        output + "/All_Solutions/" + mutation_type + "_" + str(i) + "_Signatures"
    )
    signature_subdirectory = subdirectory + "/Signatures"
    activity_subdirectory = subdirectory + "/Activities"
    stats_subdirectory = subdirectory + "/Solution_Stats"
    if not os.path.exists(subdirectory):
        os.makedirs(subdirectory)
        os.makedirs(
            signature_subdirectory
        )  # processes, processSTE and SBS Plots will go here
        os.makedirs(
            activity_subdirectory
        )  # exposures, exposureSTE, TMB plot and activity plot
        os.makedirs(stats_subdirectory)  # all others

    # preparing the column and row indeces for the Average processes and exposures:
    listOfSignatures = []
    letters = list(string.ascii_uppercase)
    letters.extend([i + b for i in letters for b in letters])
    letters = letters[0:i]

    for j, l in zip(range(i), letters):
        listOfSignatures.append(mutation_type + l)
    listOfSignatures = np.array(listOfSignatures)

    # Extract the genomes, processAVG, processStabityAvg
    genome = loopResults[0]
    processAvg = loopResults[1]
    exposureAvg = loopResults[2]
    process_stabililities = np.array(loopResults[6])
    minProcessStability = round(np.min(process_stabililities), 2)
    meanProcessStability = round(np.mean(process_stabililities), 2)

    # Calculating and listing the reconstruction error, process stability and signares to make a csv file at the end
    reconstruction_error = round(
        LA.norm(genome - np.dot(processAvg, exposureAvg), "fro")
        / LA.norm(genome, "fro"),
        4,
    )

    # First exporting the Average of the processes
    processAvg = pd.DataFrame(processAvg)
    # Convert index to list for pandas 3.12 compatibility and assign directly to index
    index_list = list(index)
    processAvg.index = index_list
    processes = processAvg
    processes.columns = listOfSignatures
    processes = processes.rename_axis("MutationType", axis="columns")
    # print(processes)
    # print("process are ok", processes)
    processes.to_csv(
        signature_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_Signatures"
        + ".txt",
        sep="\t",
        index_label=[processes.columns.name],
    )

    # Second exporting the Average of the exposures
    exposureAvg_float = pd.DataFrame(exposureAvg)
    exposures_float = exposureAvg_float.set_index(listOfSignatures)
    exposures_float.columns = colnames
    exposures_float = exposures_float.T
    exposures_float = exposures_float.rename_axis("Samples", axis="columns")

    exposureAvg_int = pd.DataFrame(exposureAvg.astype(int))
    exposures = exposureAvg_int.set_index(listOfSignatures)
    exposures.columns = colnames
    exposures = exposures.T
    exposures = exposures.rename_axis("Samples", axis="columns")
    # print("exposures are ok", exposures)
    exposures.to_csv(
        activity_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_NMF_Activities.txt",
        sep="\t",
        index_label=[exposures.columns.name],
    )

    # plt tmb
    tmb_exposures = pd.melt(exposures_float)
    tmb_exposures = pd.DataFrame(
        {
            "Types": tmb_exposures["Samples"].astype(str).to_numpy(),
            "Mut_burden": tmb_exposures["value"].to_numpy(),
        }
    )
    tmb.plotTMB(
        tmb_exposures,
        scale=sequence,
        Yrange="adapt",
        output=activity_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_"
        + "TMB_NMF_plot.pdf",
    )
    del tmb_exposures

    # plot activities
    plot_ac.plotActivity(
        activity_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_NMF_Activities.txt",
        output_file=activity_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_"
        + "NMF_Activity_Plots.pdf",
        bin_size=50,
        log=False,
    )

    # get the standard errors of the processes
    processSTE = loopResults[3]
    # export the processStd file
    processSTE = pd.DataFrame(processSTE)
    # Convert index to list for pandas 3.12 compatibility and assign directly to index
    processSTE.index = index_list
    processSTE.columns = listOfSignatures
    processSTE = processSTE.rename_axis("MutationType", axis="columns")
    processSTE.to_csv(
        signature_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_Signatures_SEM_Error"
        + ".txt",
        sep="\t",
        float_format="%.2E",
        index_label=[processes.columns.name],
    )

    # get the standard errors of the exposures
    exposureSTE = loopResults[4]
    # export the exposureStd file
    exposureSTE = pd.DataFrame(exposureSTE)
    exposureSTE = exposureSTE.set_index(listOfSignatures)
    exposureSTE.columns = colnames
    exposureSTE = exposureSTE.T
    exposureSTE = exposureSTE.rename_axis("Samples", axis="columns")
    exposureSTE.to_csv(
        activity_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_NMF_Activities_SEM_Error.txt",
        sep="\t",
        float_format="%.2E",
        index_label=[exposures.columns.name],
    )

    all_similarities = loopResults[8].copy()
    all_similarities["L1_Norm_%"] = all_similarities["L1_Norm_%"].astype(str) + "%"
    all_similarities["L2_Norm_%"] = all_similarities["L2_Norm_%"].astype(str) + "%"
    all_similarities.to_csv(
        stats_subdirectory + "/" + mutation_type + "_S" + str(i) + "_Samples_stats.txt",
        sep="\t",
    )

    signature_stats = loopResults[9]
    signature_stats = signature_stats.set_index(listOfSignatures)
    signature_stats = signature_stats.rename_axis("Signatures", axis="columns")
    signature_stats.to_csv(
        stats_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_"
        + "Signatures_stats.txt",
        sep="\t",
        index_label="Signatures",
    )

    # export convergence information
    converge_information = loopResults[13]
    converge_information = pd.DataFrame(np.around(converge_information, decimals=3))
    conv_index = list(range(1, len(converge_information) + 1))
    colmetrices = [
        "L1",
        "L1 %",
        "L2",
        "L2 %",
        "KL Divergence",
        "Correlation",
        "Convergence Iterations",
    ]
    converge_information.index = conv_index
    converge_information.columns = colmetrices
    converge_information.to_csv(
        stats_subdirectory
        + "/"
        + mutation_type
        + "_S"
        + str(i)
        + "_"
        + "NMF_Convergence_Information.txt",
        sep="\t",
        index_label="NMF_Replicate",
    )

    # export Wall and Hall if "wall" argument is true
    if wall == True:
        np.savetxt(
            stats_subdirectory + "/" + mutation_type + "_S" + str(i) + "_Wall.txt",
            Wall,
            delimiter="\t",
        )
        np.savetxt(
            stats_subdirectory + "/" + mutation_type + "_S" + str(i) + "_Hall.txt",
            Hall,
            delimiter="\t",
        )

    fh = open(output + "/All_solutions_stat.csv", "a")
    print(
        "The reconstruction error is {}, average process stability is {} and \nthe minimum process stability is {} for {} signatures\n\n".format(
            reconstruction_error,
            round(meanProcessStability, 2),
            round(minProcessStability, 2),
            i,
        )
    )
    fh.write(
        "{}, {}, {}, {}\n".format(
            i,
            round(minProcessStability, 2),
            round(reconstruction_error, 4),
            round(meanProcessStability, 2),
        )
    )
    fh.close()

    ########################################### PLOT THE SIGNATURES ################################################
    # prepare the texts lists:
    stability_list = signature_plotting_text(loopResults[6], "Stability", "float")
    total_mutation_list = signature_plotting_text(
        loopResults[7], "Sig. Mutations", "integer"
    )

    if m == "DBS78":
        plot.plotDBS(
            signature_subdirectory
            + "/"
            + mutation_type
            + "_S"
            + str(i)
            + "_Signatures"
            + ".txt",
            signature_subdirectory + "/Signature_plot/",
            "S" + str(i),
            "78",
            True,
            custom_text_upper=stability_list,
            custom_text_middle=total_mutation_list,
            volume=volume,
        )
    elif m == "ID83":
        plot.plotID(
            signature_subdirectory
            + "/"
            + mutation_type
            + "_S"
            + str(i)
            + "_Signatures"
            + ".txt",
            signature_subdirectory + "/Signature_plot/",
            "S" + str(i),
            "83",
            True,
            custom_text_upper=stability_list,
            custom_text_middle=total_mutation_list,
            volume=volume,
        )
    elif m == "CNV48":
        plot.plotCNV(
            signature_subdirectory
            + "/"
            + mutation_type
            + "_S"
            + str(i)
            + "_Signatures"
            + ".txt",
            signature_subdirectory + "/Signature_plot/",
            "S" + str(i),
            percentage=True,
            aggregate=False,
        )
    elif m == "SV32":
        plot.plotSV(
            signature_subdirectory
            + "/"
            + mutation_type
            + "_S"
            + str(i)
            + "_Signatures"
            + ".txt",
            signature_subdirectory + "/Signature_plot/",
            "S" + str(i),
            percentage=True,
            aggregate=False,
        )
    elif (
        m == "SBS96"
        or m == "SBS288"
        or m == "SBS384"
        or m == "SBS1536"
        or m == "SBS4608"
    ):
        # parse 'm' to be accepted by the plotSBS function
        tmp_m = m
        if m.startswith("SBS"):
            tmp_m = m[3:]
        if m == "SBS96" or m == "SBS288" or m == "SBS384" or m == "SBS1536":
            plot.plotSBS(
                signature_subdirectory
                + "/"
                + mutation_type
                + "_S"
                + str(i)
                + "_Signatures"
                + ".txt",
                signature_subdirectory + "/Signature_plot/",
                "S" + str(i),
                tmp_m,
                True,
                custom_text_upper=stability_list,
                custom_text_middle=total_mutation_list,
                volume=volume,
            )
        elif m == "SBS4608":
            plot.plotSBS(
                signature_subdirectory
                + "/"
                + mutation_type
                + "_S"
                + str(i)
                + "_Signatures"
                + ".txt",
                signature_subdirectory + "/Signature_plot/",
                "S" + str(i),
                tmp_m,
                True,
                custom_text_upper=stability_list,
                custom_text_middle=total_mutation_list,
            )
    else:
        custom_signatures_plot(processes, signature_subdirectory)


# #############################################################################################################
######################################### PLOTTING FUNCTIONS ##############################################
#############################################################################################################


######################################## Clustering ####################################################
def dendrogram(data, threshold, layer_directory):
    colnames = data.columns
    data = np.array(data)

    Z = hierarchy.linkage(data.T, "single", "cosine")
    plt.figure(figsize=(15, 9))
    dn = hierarchy.dendrogram(Z, labels=colnames, color_threshold=threshold)
    plt.title("Clustering of Samples Based on Mutational Signatures")
    plt.ylabel("Cosine Distance")
    plt.xlabel("Sample IDs")
    # plt.ylim((0,1))
    plt.savefig(layer_directory + "/dendrogram.pdf", figsize=(10, 8), dpi=300)
    # which datapoints goes to which cluster
    # The indices of the datapoints will be displayed as the ids
    Y = hierarchy.fcluster(Z, threshold, criterion="distance", R=None, monocrit=None)
    dataframe = pd.DataFrame({"Cluster": Y, "Sample Names": list(colnames)})
    dataframe = dataframe.set_index("Sample Names")
    # print(dataframe)
    dictionary = {"clusters": Y, "informations": dn}

    return dataframe


######################################## Plot the reconstruction error vs stabilities and select the optimum number of signature ####################################################
def stabVsRError(
    csvfile,
    output,
    title,
    all_similarities_list,
    input_type="csvfile",
    stability=0.8,
    min_stability=0.2,
    combined_stability=1.0,
    mtype="",
    statistics=True,
    select=None,
    sequence="genome",
    allow_stability_drop=False,
):
    if input_type == "csvfile":
        data = pd.read_csv(csvfile, sep=",")
    elif input_type == "dataframe":
        data = csvfile

    # exracting and preparing other similiry matrices from the all_similarities_list
    mean_cosine_dist = []
    max_cosine_dist = []
    mean_l1 = []
    maximum_l1 = []
    mean_l2 = []
    maximum_l2 = []
    mean_kl = []
    maximum_kl = []
    mean_correlation = []
    minimum_correlation = []
    # all_mean_l2=[];
    # median_l1= Median L1 , maximum _l1 = Maximum L1, median_l2= Median L2 , maximum _l2 = Maximum L2, median_kl= Median KL , maximum _kl = Maximum KL, wilcoxontest = Wilcoxontest significance (True or False); all_med_l2=[] = list of all Median L2
    # statistical test we need to set a previous L2 (pre_l2) which have a same length as the sample number

    selection_data = data.copy()
    selection_data["total_stab"] = data["Stability"] + data["avgStability"]

    try:
        selection_data_to_sort = selection_data[
            selection_data["total_stab"] >= combined_stability
        ]
        selection_data_to_sort = selection_data_to_sort[
            selection_data_to_sort["Stability"] >= min_stability
        ]
        selection_data_to_sort = selection_data_to_sort[
            selection_data_to_sort["avgStability"] >= stability
        ]
        highest_stable_idx = selection_data_to_sort.index[-1]
    except:  # if there is no solution over thresh-hold
        selection_data_to_sort = selection_data
        highest_stable_idx = selection_data.index[0]
        print(
            "There is no signature over the thresh-hold stability. We are selecting the lowest possible number of signatures."
        )

    highest_stable_signature = list(selection_data["Total Signatures"])[
        highest_stable_idx
    ]
    selection_data = selection_data_to_sort.sort_values(
        by=["avgStability", "Total Signatures"], ascending=[False, True]
    )
    resorted_idx = list(selection_data.index)
    default_idx = resorted_idx.index(highest_stable_idx)
    if allow_stability_drop == False:
        selected_resorted_idx = resorted_idx[0 : default_idx + 1]
    else:
        selected_resorted_idx = resorted_idx
    selected_resorted_idx.sort()
    idx_within_thresh_hold = highest_stable_idx
    signatures_within_thresh_hold = highest_stable_signature
    # create probability list
    probabilities = ["N/A"] * len(all_similarities_list)
    stable_solutions = ["NO"] * len(all_similarities_list)

    for values in range(
        len(all_similarities_list)
    ):  # loop through the opposite direction
        all_similarities = all_similarities_list[values].iloc[:, [1, 3, 5, 6, 7]]

        cosine_distance = 1 - all_similarities["Cosine Similarity"]
        mean_cosine_dist.append(round(cosine_distance.mean(), 3))
        max_cosine_dist.append(round(cosine_distance.max(), 3))
        mean_l1.append(round(all_similarities["L1_Norm_%"].median(), 2))
        maximum_l1.append(round(all_similarities["L1_Norm_%"].max(), 2))
        mean_l2.append(round(all_similarities["L2_Norm_%"].median(), 2))
        maximum_l2.append(round(all_similarities["L2_Norm_%"].max(), 2))
        mean_kl.append(round(all_similarities["KL Divergence"].mean(), 4))
        maximum_kl.append(round(all_similarities["KL Divergence"].max(), 4))
        mean_correlation.append(round(all_similarities["Correlation"].mean(), 3))
        minimum_correlation.append(round(all_similarities["Correlation"].min(), 3))

    all_similarities = all_similarities_list[idx_within_thresh_hold].iloc[
        :, [1, 3, 5, 6, 7]
    ]
    # record the statistical test between the l2_of the current and previous signatures first
    init_l2_dist = all_similarities["L2_Norm_%"]
    init_mean = all_similarities["L2_Norm_%"].median()
    probabilities[idx_within_thresh_hold] = "Most Stab Sigs"
    stable_solutions[idx_within_thresh_hold] = "YES"
    # select the final solution. Don't go to the while loop if there is not more than 1 signatures over thresh-hold
    list_of_idx_over_thresh_hold = selected_resorted_idx
    strating_idx = len(list_of_idx_over_thresh_hold) - 1
    if len(list_of_idx_over_thresh_hold) > 1 and statistics == True:
        while True:
            idx_within_thresh_hold = list_of_idx_over_thresh_hold[strating_idx - 1]
            signatures_within_thresh_hold = signatures_within_thresh_hold - (
                list_of_idx_over_thresh_hold[strating_idx]
                - list_of_idx_over_thresh_hold[strating_idx - 1]
            )  # get the difference between current and previous stable signatures
            all_similarities = all_similarities_list[idx_within_thresh_hold].iloc[
                :, [1, 3, 5, 6, 7]
            ]
            current_l2_dist = all_similarities["L2_Norm_%"]
            current_mean = all_similarities["L2_Norm_%"].median()
            wiltest = ranksums(np.array(init_l2_dist), np.array(current_l2_dist))[1]
            # p_value threshold for wiltest
            if sequence == "exome":
                wiltest_thr = 1.0
            else:
                wiltest_thr = 0.05
            probabilities[idx_within_thresh_hold] = "{:.2e}".format(wiltest)
            stable_solutions[idx_within_thresh_hold] = "YES"
            if (
                (wiltest < wiltest_thr)
                and (current_mean - init_mean > 0)
                or idx_within_thresh_hold == 0
            ):
                final_solution = signatures_within_thresh_hold + (
                    list_of_idx_over_thresh_hold[strating_idx]
                    - list_of_idx_over_thresh_hold[strating_idx - 1]
                )  # select the previous stable signatures
                break
            strating_idx = strating_idx - 1

    else:
        final_solution = signatures_within_thresh_hold

    if type(select) != type(None):
        final_solution = select

    data.iloc[:, 2] = np.round(data.iloc[:, 2] * 100, 2)
    data = data.assign(
        **{
            "Mean Sample L1%": mean_l1,
            "Maximum Sample L1%": maximum_l1,
            "Mean Sample L2%": mean_l2,
            "Maximum Sample L2%": maximum_l2,
            "Mean Sample KL": mean_kl,
            "Maximum Sample KL": maximum_kl,
            "Mean Cosine Distance": mean_cosine_dist,
            "Max Cosine Distance": max_cosine_dist,
            "Mean Correlation": mean_correlation,
            "Minimum Correlation": minimum_correlation,
        }
    )

    data = data.rename(columns={"Stability": "Minimum Stability"})
    data = data.set_index("Total Signatures")

    # get the solution
    probable_solutions = data.copy()
    avg_stability = data.iloc[:, 2]
    data = data.drop(columns="avgStability")
    try:
        alternative_solution = int(final_solution)
    except:
        alternative_solution = int(data.index[0])
        print(
            "There is no solution over the thresh-hold minimum stability. We are selecting the minimum number of signature which could be wrong."
        )
    # ---------------------------- alternative solution end -------------------------------------------------#
    # Create some mock data

    t = np.array(data.index).astype(int)

    # data1 = np.array(data.iloc[:,2])  #reconstruction error
    data1 = np.array(mean_cosine_dist)
    data2 = np.array(avg_stability)  # process stability
    shadow_alternative_start = alternative_solution - 0.2
    shadow_alternative_end = alternative_solution + 0.2
    fig, ax1 = plt.subplots(
        num=None, figsize=(10, 6), dpi=300, facecolor="w", edgecolor="k"
    )
    color = "tab:red"
    ax1.set_xlabel("Total Signatures")
    ax1.set_ylabel("Mean Sample Cosine Distance", color=color)
    ax1.set_title(title)
    lns1 = ax1.plot(
        t,
        data1,
        marker="o",
        linestyle=":",
        color=color,
        label="Mean Sample Cosine Distance",
    )
    ax1.tick_params(axis="y", labelcolor=color)
    ax1.xaxis.set_ticks(np.arange(min(t), max(t) + 1, 1))
    ax1.axvspan(
        shadow_alternative_start, shadow_alternative_end, alpha=0.20, color="#696969"
    )
    # manipulate the y-axis values into percentage
    vals = ax1.get_yticks()
    # ax1.set_xticklabels(np.arange(min(t), max(t)+1, 1),list(), rotation=30)
    ax1.set_xticklabels(list(np.arange(min(t), max(t) + 1, 1)), rotation=30)
    ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
    color = "tab:blue"
    ax2.set_ylabel(
        "Avg Stability", color=color
    )  # we already handled the x-label with ax1
    lns2 = ax2.plot(
        t, data2, marker="s", linestyle="-.", color=color, label="Avg Stability"
    )
    ax2.tick_params(axis="y", labelcolor=color)
    fig.tight_layout()  # otherwise the right y-label is slightly clipped
    # plt.show()
    lns = lns1 + lns2
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc=0)
    plt.savefig(output + "/" + mtype + "_selection_plot.pdf")
    plt.close()
    # put * in the selected solution
    index = data.index.astype(int)
    index = list(index.astype(str))
    solution = get_indeces(index, [str(alternative_solution)])[0]
    index[solution] = index[solution] + "*"
    data.index = index

    # add % signs
    data.insert(1, "Considerable Solution", stable_solutions)
    data.insert(2, "P-value", probabilities)
    # Convert columns to object dtype first before assigning string values (pandas 3.12 requirement)
    # iloc assignment doesn't allow dtype changes, so we need to convert by column name
    for col_idx in range(3, 7):
        col_name = data.columns[col_idx]
        data[col_name] = data[col_name].astype(str) + "%"
    data = data.reset_index()
    columns_list = list(data.columns)
    columns_list[0] = "Signatures"
    data.columns = columns_list
    return alternative_solution, data


######################################## Plot Samples ####################################################
def plot_csv_sbs_samples(
    filename, output_path, project, mtype="96", percentage=False, custom_text_upper=" "
):
    data, index, colnames, _ = read_csv(filename, folder=False)
    data.index.names = ["MutationType"]
    data.to_csv("new_file.text", sep="\t")
    plot.plotSBS(
        "new_file.text", output_path, project, mtype, False, custom_text_upper=" "
    )
    os.remove("new_file.text")


def evaluation(true_sigs, est_sigs, cutoff=0.9, dist="cos", verbose=False):
    if true_sigs.shape[1] >= est_sigs.shape[1]:
        mat1 = est_sigs
        mat2 = true_sigs
    else:
        mat1 = true_sigs
        mat2 = est_sigs

    if dist == "cos":
        con_mat = cdist(mat1.T, mat2.T, "cosine")
    elif dist == "cor":
        con_mat = cdist(mat1.T, mat2.T, "correlation")
    row_ind, col_ind = linear_sum_assignment(con_mat)
    # print(con_mat[row_ind, col_ind].sum())
    con_mat = 1 - con_mat
    idxPair = {}
    true_positives = 0
    for x, y in zip(row_ind, col_ind):
        idxPair[x] = y
        if con_mat[x, y] >= cutoff:
            true_positives += 1

    computedFalsePositives = mat1.shape[1] - true_positives
    # print(computedFalsePositives)
    computedFalseNegatives = computedFalsePositives
    # print(computedFalseNegatives)
    if true_sigs.shape[1] >= est_sigs.shape[1]:
        baseFalsePositives = 0
        baseFalseNegatives = true_sigs.shape[1] - est_sigs.shape[1]

    elif est_sigs.shape[1] > true_sigs.shape[1]:
        baseFalsePositives = est_sigs.shape[1] - true_sigs.shape[1]
        baseFalseNegatives = 0

    false_positives = baseFalsePositives + computedFalsePositives
    false_negatives = baseFalseNegatives + computedFalseNegatives
    number_of_ground_truth_signatures = true_sigs.shape[1]
    number_of_detected_signature = est_sigs.shape[1]
    try:
        precision = round(true_positives / (true_positives + false_positives), 2)
        recall = round(true_positives / (true_positives + false_negatives), 2)
        f1_score = round(2 * precision * recall / (precision + recall), 2)
    except:
        precision = 0
        recall = 0
        f1_score = 0

    return (
        number_of_ground_truth_signatures,
        number_of_detected_signature,
        true_positives,
        false_positives,
        false_negatives,
        precision,
        recall,
        f1_score,
        idxPair,
    )


def custom_signatures_plot(signatures, output):
    with PdfPages(output + "/Custom_Signature_Plots.pdf") as pdf:
        plt.figure(figsize=(10, 3))
        plt.bar(list(range(1, 1 + len(signatures.iloc[:, 0]))), signatures.iloc[:, 0])
        plt.title("Custom Signature {}".format(0 + 1))
        plt.xticks([])
        plt.xlabel("Mutation Types")
        plt.ylabel("Probabilities")
        pdf.savefig()  # saves the current figure into a pdf page
        plt.close()
        for i in range(1, signatures.shape[1]):
            # if LaTeX is not installed or error caught, change to `usetex=False`
            plt.rc("text", usetex=False)
            plt.figure(figsize=(10, 3))
            plt.bar(
                list(range(1, 1 + len(signatures.iloc[:, i]))), signatures.iloc[:, i]
            )
            plt.title("Custom Signature {}".format(i + 1))
            plt.xticks([])
            plt.xlabel("Mutation Types")
            plt.ylabel("Probabilities")
            pdf.attach_note("signature plots")
            pdf.savefig()
            plt.close()
