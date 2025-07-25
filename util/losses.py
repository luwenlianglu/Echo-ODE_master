import os
from math import exp
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

'''
 weight = torch.tensor([2.72, 16.5, 4.39, 143.95, 118.48, 82.47, 524.25, 145.44, 6.24, 67.98, 23.85, 88.5, 1040.56, 14.73, 761.47,390.39, 457.47, 626.6, 318.81]).cuda()
'''

CROSS_ENTROPY_LOSS = 'ce'
FOCAL_LOSS = 'focal'
ADA_BOUND_LOSS = 'adabound'
MSE_LOSS = 'mse'
BCE_LOSS = 'bce'
BCE_LOGIT_LOSS = 'bce-logit'
SSIM_LOSS = 'ssim'


def get_loss_function(mode=CROSS_ENTROPY_LOSS, weight=None, alpha=1, gamma=2, ignore_index=255):
    if mode=='ce':
        loss = nn.CrossEntropyLoss(weight=weight, ignore_index=ignore_index)
    elif mode=='focal':
        loss = FocalLoss2d(weight=weight, gamma=gamma)#weight=weight**(alpha)
    elif mode=='dice':
        loss=MultiClassDiceLoss()

    return loss

def get_reconstruction_loss_function(mode=MSE_LOSS):

    if mode==MSE_LOSS:
        loss = nn.MSELoss()
    elif mode==BCE_LOSS:
        loss = nn.BCELoss()
    elif mode==BCE_LOGIT_LOSS:
        loss = nn.BCEWithLogitsLoss()
    elif mode==SSIM_LOSS:
        loss = SSIM()

    return loss

class FocalLoss2d(nn.Module):
    """
    Work taken from https://github.com/c0nn3r/RetinaNet/blob/master/focal_loss.py
    """
    def __init__(self, weight=None, gamma=0, size_average=True, ignore_index=255):
        super(FocalLoss2d, self).__init__()

        self.gamma = gamma
        self.weight = weight
        self.size_average = size_average
        self.ignore_index = ignore_index

    def forward(self, input, target):
        if input.dim()>2:
            input = input.contiguous().view(input.size(0), input.size(1), -1)
            input = input.transpose(1,2)
            input = input.contiguous().view(-1, input.size(2)).squeeze()
        if target.dim()==4:
            target = target.contiguous().view(target.size(0), target.size(1), -1)
            target = target.transpose(1,2)
            target = target.contiguous().view(-1, target.size(2)).squeeze()
        elif target.dim()==3:
            target = target.view(-1)
        else:
            target = target.view(-1, 1)

        # compute the negative likelyhood
        # weight = Variable(self.weight)
        logpt = -F.cross_entropy(input, target, weight=self.weight, ignore_index=self.ignore_index)
        pt = torch.exp(logpt)

        # compute the loss
        loss = -((1-pt)**self.gamma) * logpt

        # averaging (or not) loss
        if self.size_average:
            return loss.mean()
        else:
            return loss.sum()

class SSIM(torch.nn.Module):
    """
    Work taken from: https://github.com/Po-Hsun-Su/pytorch-ssim
    """
    def __init__(self, window_size=11, size_average=True):
        super(SSIM, self).__init__()
        self.window_size = window_size
        self.size_average = size_average
        self.channel = 1
        self.window = self.create_window(window_size, self.channel)

    def gaussian(self, window_size, sigma):
        gauss = torch.Tensor([exp(-(x - window_size // 2) ** 2 / float(2 * sigma ** 2)) for x in range(window_size)])
        return gauss / gauss.sum()

    def create_window(self, window_size, channel):
        _1D_window = self.gaussian(window_size, 1.5).unsqueeze(1)
        _2D_window = _1D_window.mm(_1D_window.t()).float().unsqueeze(0).unsqueeze(0)
        window = _2D_window.expand(channel, 1, window_size, window_size).contiguous()
        return window

    def _ssim(self, img1, img2, window, window_size, channel, size_average=True):
        mu1 = F.conv2d(img1, window, padding=window_size // 2, groups=channel)
        mu2 = F.conv2d(img2, window, padding=window_size // 2, groups=channel)

        mu1_sq = mu1.pow(2)
        mu2_sq = mu2.pow(2)
        mu1_mu2 = mu1 * mu2

        sigma1_sq = F.conv2d(img1 * img1, window, padding=window_size // 2, groups=channel) - mu1_sq
        sigma2_sq = F.conv2d(img2 * img2, window, padding=window_size // 2, groups=channel) - mu2_sq
        sigma12 = F.conv2d(img1 * img2, window, padding=window_size // 2, groups=channel) - mu1_mu2

        C1 = 0.01 ** 2
        C2 = 0.03 ** 2

        ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

        if size_average:
            return ssim_map.mean()
        else:
            return ssim_map.mean(1).mean(1).mean(1)

    def forward(self, img1, img2):
        (_, channel, _, _) = img1.size()

        if channel == self.channel and self.window.data.type() == img1.data.type():
            window = self.window
        else:
            window = self.create_window(self.window_size, channel)

            if img1.is_cuda:
                window = window.cuda(img1.get_device())
            window = window.type_as(img1)

            self.window = window
            self.channel = channel

        return - self._ssim(img1, img2, window, self.window_size, channel, self.size_average)

class BinaryDiceLoss(nn.Module):
    def __init__(self, smooth=1):
        super(BinaryDiceLoss, self).__init__()
        self.smooth=smooth
    def forward(self,input,target):
        bs=input.size(0)
        input_flat=input.view(bs,-1)
        target_flat=target.view(bs,-1)

        intersection=input_flat*target_flat
        dice_eff=(2*intersection.sum(1)+self.smooth)/(input_flat.sum(1)+target_flat.sum(1)+self.smooth)
        return 1-dice_eff.sum()/bs
class MultiClassDiceLoss(nn.Module):
    def __init__(self,weight=None,ignore_index=255):
        super(MultiClassDiceLoss, self).__init__()
        self.weight=weight
        self.ignore_index=ignore_index
    def forward(self,input,target):
        """
        Args:
            input: of shape = [N,C,H,W]
            target: of shape = [N,H,W]

        Returns: dice loss

        """
        nclass,h,w=input.size(1),input.size(2),input.size(3)
        input=F.softmax(input,dim=1)


        binary_dice=BinaryDiceLoss()
        total_loss=0
        for i in range(nclass):
            # targetclass=target[target==i]
            total_loss+=binary_dice(input[:,i], target==i)
        return total_loss/nclass

