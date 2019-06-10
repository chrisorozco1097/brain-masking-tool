import argparse
import os
import cv2
import sys
import glob
import numpy as np
from tqdm import tqdm
from medpy.io import load, save
from models.model import Unet
from skimage.transform import resize

# parse arguments
parser = argparse.ArgumentParser()

parser.add_argument('--target-dir',
        nargs='?',
        default='images/',
        help='path to the dir that contains images, it will recursivelly look for all .nii images and provide a mask for them, defaults to the images directory in the project.')

args = parser.parse_args()
target_dir = args.target_dir
model_type = 'unet'

def __normalize0_255(img_slice):
    '''Normalizes the image to be in the range of 0-255
    it round up negative values to 0 and caps the top values at the
    97% value as to avoid outliers'''
    img_slice[img_slice < 0] = 0
    flat_sorted = np.sort(img_slice.flatten())

    #dont consider values greater than 97% of the values
    top_3_limit = int(len(flat_sorted) * 0.97)
    limit = flat_sorted[top_3_limit]

    img_slice[img_slice > limit] = limit

    rows, cols = img_slice.shape
    #create new empty image
    new_img = np.zeros((rows, cols))
    max_val = np.max(img_slice)
    if max_val == 0:
        return new_img

    #normalize all values
    for i in range(rows):
        for j in range(cols):
            new_img[i,j] = int((
                float(img_slice[i,j])/float(max_val)) * 255)

    return new_img

def getImageData(fname):
    '''Returns the image data, image matrix and header of
    a particular file'''
    data, hdr = load(fname)
    # axes have to be switched from (256,256,x) to (x,256,256)
    data = np.moveaxis(data, -1, 0)

    norm_data = []
    # normalize each image slice
    for i in range(data.shape[0]):
        img_slice = data[i,:,:]
        norm_data.append(__normalize0_255(img_slice))

    # remake 3D representation of the image
    data = np.array(norm_data, dtype=np.uint16)

    data = data[..., np.newaxis]
    return data, hdr

def resizeData(image, target=(256, 256)):
    image = np.squeeze(image)
    resized_img = []
    for i in range(image.shape[0]):
        img_slice = cv2.resize(image[i,:,:], target)
        resized_img.append(img_slice)

    image = np.array(resized_img, dtype=np.uint16)

    return image[..., np.newaxis]

# get all files in target dir that end with nii
files = glob.glob(target_dir+'/**/*.nii', recursive=True)

# ignore masks
files = [f for f in files if 'mask.nii' not in f]

print('Found %d NIFTI files'%len(files))

if len(files) == 0:
    print('No NIFTI files found, exiting')
    sys.exit(0)

if model_type == 'unet':
    print('Loading Unet model')
    model = Unet()

skipped = []
for img_path in tqdm(files):
    img, hdr = getImageData(img_path)
    resizeNeeded = False

    if model_type == 'unet':
        if img.shape[1] != 256 and img.shape[2] != 256:
            original_shape = (img.shape[2], img.shape[1])
            img = resizeData(img)
            resizeNeeded = True


    res = model.predict_mask(img)

    if resizeNeeded:
        res = resizeData(res, target=original_shape)

    # remove extra dimension
    res = np.squeeze(res)

    # return result into shape (256,256, X)
    res = np.moveaxis(res, 0, -1)

    # Save result
    img_path = img_path[:img_path.rfind('.')]
    save(res, img_path + '_mask.nii', hdr)

skipped_file = open("skipped.txt","w+")
skipped_file.writelines(skipped)
skipped_file.close()

if len(skipped) > 0:
    print('Skipped %d images, Unet can only work with 256x256/512x512 images for now'%len(skipped))
