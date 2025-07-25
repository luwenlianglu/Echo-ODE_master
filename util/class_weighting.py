import os
import torch
from tqdm import tqdm
import numpy as np


def get_class_weights(dataloader, num_classes, mode=''):
    if mode == 'enet':
        return enet_weighing(dataloader, num_classes)
    elif mode == 'median-freq':
        return median_freq_balancing(dataloader, num_classes)
    elif mode == 'github-found':
        return github_found()


def enet_weighing(dataloader, num_classes, c=1.02):
    """Computes class weights as described in the ENet paper:
        w_class = 1 / (ln(c + p_class)),
    where c is usually 1.02 and p_class is the propensity score of that
    class:
        propensity_score = freq_class / total_pixels.
    References: https://arxiv.org/abs/1606.02147
    Keyword arguments:
    - dataloader (``data.Dataloader``): A data loader to iterate over the
    dataset.
    - num_classes (``int``): The number of classes.
    - c (``int``, optional): AN additional hyper-parameter which restricts
    the interval of values for the weights. Default: 1.02.
    """
    classes_weights_path = os.path.join('dataloader/enet_classes_weights.npy')

    if os.path.isfile(classes_weights_path):
        weight = np.load(classes_weights_path)
        weight = torch.from_numpy(weight.astype(np.float32)).cuda()

        return weight

    class_count = 0
    total = 0
    tbar = tqdm(dataloader)

    for i, sample in enumerate(tbar):
        label = sample[1]
        label = label.cpu().numpy()

        # Flatten label
        flat_label = label.flatten()

        # Sum up the number of pixels of each class and the total pixel
        # counts for each label
        class_count += np.bincount(flat_label, minlength=num_classes)
        total += flat_label.size


    # Compute propensity score and then the weights for each class
    new_class_count = class_count[0:num_classes]
    propensity_score = new_class_count / total
    class_weights = 1 / (np.log(c + propensity_score))
    np.save(classes_weights_path, class_weights)

    return torch.from_numpy(class_weights.astype(np.float32)).cuda()


def median_freq_balancing(dataloader, num_classes):
    """Computes class weights using median frequency balancing as described
    in https://arxiv.org/abs/1411.4734:
        w_class = median_freq / freq_class,
    where freq_class is the number of pixels of a given class divided by
    the total number of pixels in images where that class is present, and
    median_freq is the median of freq_class.
    Keyword arguments:
    - dataloader (``data.Dataloader``): A data loader to iterate over the
    dataset.
    whose weights are going to be computed.
    - num_classes (``int``): The number of classes
    """
    classes_weights_path = os.path.join("../datasets/cityscapes/" + 'median-freq_classes_weights.npy')

    if os.path.isfile(classes_weights_path):
        weight = np.load(classes_weights_path)
        weight = torch.from_numpy(weight.astype(np.float32)).cuda()

        return weight

    class_count = 0
    total = 0
    tbar = tqdm(dataloader)

    for i, sample in enumerate(tbar):
        label = sample[1]
        label = label.cpu().numpy()

        # Flatten label
        flat_label = label.flatten()

        # Sum up the class frequencies
        bincount = np.bincount(flat_label, minlength=num_classes)
        bincount = bincount[0:19]

        # Create of mask of classes that exist in the label
        mask = bincount > 0
        # Multiply the mask by the pixel count. The resulting array has
        # one element for each class. The value is either 0 (if the class
        # does not exist in the label) or equal to the pixel count (if
        # the class exists in the label)
        total += mask * flat_label.size

        # Sum up the number of pixels found for each class
        class_count += bincount

    # Compute the frequency and its median
    freq = class_count / total
    med = np.median(freq)
    class_weights = med /freq
    np.save(classes_weights_path, class_weights)

    return torch.from_numpy(class_weights.astype(np.float32)).cuda()

def github_found():
    classes_weights_path = os.path.join("../datasets/cityscapes/" + 'cityscapes_classes_weights.npy')

    if os.path.isfile(classes_weights_path):
        weight = np.load(classes_weights_path)
        weight = torch.from_numpy(weight.astype(np.float32)).cuda()
    else:
        raise Exception('Did not find Github-found class weights')
    return weight
