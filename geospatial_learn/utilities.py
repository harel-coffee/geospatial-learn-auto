# -*- coding: utf-8 -*-
"""
Created on Thu Sep  8 22:35:39 2016
@author: Ciaran Robb
The utilities module - things here don't have an exact theme or home yet so
may eventually move elsewhere
Aberytswyth Uni
Wales

If you use code to publish work cite/acknowledge me and authors of libs etc as 
appropriate 
"""

import numpy as np
from scipy.spatial import ConvexHull
#from scipy.ndimage.interpolation import rotate
from skimage import exposure
from scipy import ndimage as ndi
import cv2
import matplotlib.pyplot as plt
from geospatial_learn.geodata import _copy_dataset_config, polygonize, array2raster
import gdal, ogr
from tqdm import tqdm
from skimage.feature import match_template
from skimage.color import rgb2gray
from skimage import io
import matplotlib
matplotlib.use('Qt5Agg')
import napari
import dask.array as da
from skimage.measure import regionprops
from skimage import color
#import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import ImageGrid
from scipy.ndimage import gaussian_filter

from skimage.transform import rescale
from skimage.feature import canny
from skimage.measure import LineModelND, ransac
#from skimage.draw import line
from warnings import warn
from scipy.interpolate import RectBivariateSpline
from skimage.util import img_as_float, invert
from skimage.filters import sobel
from skimage.morphology import remove_small_objects, remove_small_holes, medial_axis, skeletonize
import scipy.ndimage as nd
from morphsnakes import morphological_geodesic_active_contour as gac
from morphsnakes import morphological_chan_vese as mcv
from morphsnakes import inverse_gaussian_gradient
#import multiprocessing as mp
gdal.UseExceptions()
ogr.UseExceptions()



def iou_score(inSeg, trueSeg):
    # The Intersection over Union (IoU) metric, also referred to as the Jaccard index
    intersection = np.logical_and(trueVals, predVals)
    union = np.logical_or(trueVals, predVals)
    iou_score = np.sum(intersection) / np.sum(union)



def _fix_overlapping_levelsets(levelsets):
    
    # many thanks to pmneila for this 
    # Find the areas where levelsets overlap
    mask = np.sum(levelsets, axis=0) > 1

    # Set overlapping regions to 0.
    for ls in levelsets:
        ls[mask] = 0

    return levelsets

def raster2array(inRas, bands=[1]):
    
    """
    Read a raster and return an array, either single or multiband

    
    Parameters
    ----------
    
    inRas: string
                  input  raster
        
    bands: list
                  a list of bands to return in the array
    
    """
    rds = gdal.Open(inRas)
   
   
    if len(bands) ==1:
        # then we needn't bother with all the crap below
        inArray = rds.GetRasterBand(bands[0]).ReadAsArray()
        
    else:
        #   The nump and gdal dtype (ints)
        #   {"uint8": 1,"int8": 1,"uint16": 2,"int16": 3,"uint32": 4,"int32": 5,
        #    "float32": 6, "float64": 7, "complex64": 10, "complex128": 11}
        
        # a numpy gdal conversion dict - this seems a bit long-winded
        dtypes = {"1": np.uint8, "2": np.uint16,
              "3": np.int16, "4": np.uint32,"5": np.int32,
              "6": np.float32,"7": np.float64,"10": np.complex64,
              "11": np.complex128}
        rdsDtype = rds.GetRasterBand(1).DataType
        inDt = dtypes[str(rdsDtype)]
        
        inArray = np.zeros((rds.RasterYSize, rds.RasterXSize, len(bands)), dtype=inDt) 
        for band in bands:  
            rA = rds.GetRasterBand(band).ReadAsArray()
            inArray[:, :, band-1]=rA
   
   
    return inArray

def ms_toposnakes(inSeg, inRas, outShp, iterations=100, algo='GAC', band=2,
                  sigma=4, smooth=1, lambda1=1, lambda2=1, threshold='auto', 
                  balloon=-1):
    
    """
    Topology preserveing morphsnakes (kind of!) using an approximation of the
    homotopic skeleton to prevent merging of blobs
    
    
    This uses morphsnakes and explanations are from there.
    
    Parameters
    ----------
    
    inSeg: string
                  input segmentation raster
        
    raster_path: string
                  input raster whose pixel vals will be used

    band: int
           an integer val eg - 2

    algo: string
           either "GAC" (geodesic active contours) or "ACWE" (active contours without edges)
           
    sigma: the size of stdv defining the gaussian envelope if using canny edge
              a unitless value

    iterations: uint
        Number of iterations to run.
        
    smooth : uint, optional
    
        Number of times the smoothing operator is applied per iteration.
        Reasonable values are around 1-4. Larger values lead to smoother
        segmentations.
    
    lambda1: float, optional
    
        Weight parameter for the outer region. If `lambda1` is larger than
        `lambda2`, the outer region will contain a larger range of values than
        the inner region.
        
    lambda2: float, optional
    
        Weight parameter for the inner region. If `lambda2` is larger than
        `lambda1`, the inner region will contain a larger range of values than
        the outer region.
    
    threshold: float, optional
    
        Areas of the image with a value smaller than this threshold will be
        considered borders. The evolution of the contour will stop in this
        areas.
        
    balloon: float, optional
    
        Balloon force to guide the contour in non-informative areas of the
        image, i.e., areas where the gradient of the image is too small to push
        the contour towards a border. A negative value will shrink the contour,
        while a positive value will expand the contour in these areas. Setting
        this to zero will disable the balloon force.
        
    """    


    rds1 = gdal.Open(inRas)
    img = rds1.GetRasterBand(band).ReadAsArray()
    
    rds2 = gdal.Open(inSeg)
    seg = rds2.GetRasterBand(1).ReadAsArray()
    
    #img = np.float32(img)
    #img[img==0]=np.nan
#    
#    cnt = list(np.unique(seg))
#    
#    cnt.pop(0)
#    levelsets = [seg==s for s in cnt]
#    
    iters = np.arange(iterations)
    
    orig = seg>0
    
    # An approximation of the morphsnake turbopixel idea where the blobs
    # are prevented from merging by the skeleton of the background image which
    # is updated at every iteration - downside is that we always have a pixel gap
    # TODO rectify pixel gap issue
    
    if algo=='GAC':
        
        gimg = inverse_gaussian_gradient(img,sigma=4)
        
        for i in tqdm(iters):          
            # get the skeleton of the background of the prev seg
            inv = invert(orig)
            sk = skeletonize(inv)
            bw = gac(gimg, iterations=1, init_level_set=orig, smoothing=smooth,
                     threshold=threshold)
            # approximation of homotopic skel in paper 
            # we still have endpoint issue at times but it is not bad...
            bw[sk==1]=0
            # why do this? I think seg=bw will result in a pointer....
            orig = np.zeros_like(bw, dtype=np.bool)
            orig[bw==1]=1
            del inv, sk
            
    else:
        
        for i in tqdm(iters):
            inv = invert(orig)
            sk = skeletonize(inv)            
            bw = mcv(img, iterations=1,init_level_set=orig, smoothing=smooth, lambda1=1,
                lambda2=1)
            bw[sk==1]=0
            # why do this? I think seg=bw will result in a pointer....
            orig = np.zeros_like(bw, dtype=np.bool)
            orig[bw==1]=1
            del inv, sk
   
# original way which was too slow....       
# Evolve each level set a few iterations (1 in this case, it can be also 2 or 3…)
#            levelsets = [mcv(img, iterations=1,
#                               init_level_set=ls,
#                               smoothing=1, lambda1=1, lambda2=1) for ls in levelsets]
#            levelsets = _fix_overlapping_levelsets(levelsets)
    
    newseg, _ = nd.label(bw)
    
#    for idx,l in enumerate(levelsets):
#        newseg[l>0]=cnt[idx]
    
    array2raster(newseg, 1, inSeg, inSeg[:-4]+'tsnake.tif', gdal.GDT_Int32)
    
    
    
    polygonize(inSeg[:-4]+'tsnake.tif', outShp, outField=None,  mask = True, band = 1)
    
    

def combine_hough_seg(inRas1, inRas2, outRas, outShp, min_area=None):
    
    
    rds1 = gdal.Open(inRas1, gdal.GA_ReadOnly)

    rb1 = rds1.GetRasterBand(1).ReadAsArray()
    
    rds2 = gdal.Open(inRas2, gdal.GA_ReadOnly)

    rb2 = rds2.GetRasterBand(1).ReadAsArray()
    
    rgt = rds1.GetGeoTransform()
        
    pixel_res = rgt[1]
    
    oot = rb1*rb2
    
    sg, _ = nd.label(oot)
    
    if min_area != None:
        min_final = np.round(min_area/(pixel_res*pixel_res))
        
        if min_final <= 0:
            min_final=4
        
        remove_small_objects(sg, min_size=min_final, in_place=True)
    
    
    array2raster(sg, 1, inRas1, outRas,  gdal.GDT_Int32)
    
    
    polygonize(outRas, outShp, outField=None,  mask = True, band = 1)
    

def active_contour(image, snake, alpha=0.01, beta=0.1,
                   w_line=0, w_edge=1, gamma=0.01,
                   bc=None, max_px_move=1.0,
                   max_iterations=2500, convergence=0.1,
                   *,
                   boundary_condition='periodic',
                   coordinates=None):
    """Active contour model.
    Active contours by fitting snakes to features of images. Supports single
    and multichannel 2D images. Snakes can be periodic (for segmentation) or
    have fixed and/or free ends.
    The output snake has the same length as the input boundary.
    As the number of points is constant, make sure that the initial snake
    has enough points to capture the details of the final contour.
    Parameters
    ----------
    image : (N, M) or (N, M, 3) ndarray
        Input image.
    snake : (N, 2) ndarray
        Initial snake coordinates. For periodic boundary conditions, endpoints
        must not be duplicated.
    alpha : float, optional
        Snake length shape parameter. Higher values makes snake contract
        faster.
    beta : float, optional
        Snake smoothness shape parameter. Higher values makes snake smoother.
    w_line : float, optional
        Controls attraction to brightness. Use negative values to attract toward
        dark regions.
    w_edge : float, optional
        Controls attraction to edges. Use negative values to repel snake from
        edges.
    gamma : float, optional
        Explicit time stepping parameter.
    bc : deprecated; use ``boundary_condition``
        DEPRECATED. See ``boundary_condition`` below.
    max_px_move : float, optional
        Maximum pixel distance to move per iteration.
    max_iterations : int, optional
        Maximum iterations to optimize snake shape.
    convergence : float, optional
        Convergence criteria.
    boundary_condition : string, optional
        Boundary conditions for the contour. Can be one of 'periodic',
        'free', 'fixed', 'free-fixed', or 'fixed-free'. 'periodic' attaches
        the two ends of the snake, 'fixed' holds the end-points in place,
        and 'free' allows free movement of the ends. 'fixed' and 'free' can
        be combined by parsing 'fixed-free', 'free-fixed'. Parsing
        'fixed-fixed' or 'free-free' yields same behaviour as 'fixed' and
        'free', respectively.
    coordinates : {'rc' or 'xy'}, optional
        Whether to use rc or xy coordinates. The 'xy' option (current default)
        will be removed in version 0.18.
    Returns
    -------
    snake : (N, 2) ndarray
        Optimised snake, same shape as input parameter.
    References
    ----------
    .. [1]  Kass, M.; Witkin, A.; Terzopoulos, D. "Snakes: Active contour
            models". International Journal of Computer Vision 1 (4): 321
            (1988). :DOI:`10.1007/BF00133570`
    Examples
    --------
    >>> from skimage.draw import circle_perimeter
    >>> from skimage.filters import gaussian
    Create and smooth image:
    >>> img = np.zeros((100, 100))
    >>> rr, cc = circle_perimeter(35, 45, 25)
    >>> img[rr, cc] = 1
    >>> img = gaussian(img, 2)
    Initialize spline:
    >>> s = np.linspace(0, 2*np.pi, 100)
    >>> init = 50 * np.array([np.sin(s), np.cos(s)]).T + 50
    Fit spline to image:
    >>> snake = active_contour(img, init, w_edge=0, w_line=1, coordinates='rc')  # doctest: +SKIP
    >>> dist = np.sqrt((45-snake[:, 0])**2 + (35-snake[:, 1])**2)  # doctest: +SKIP
    >>> int(np.mean(dist))  # doctest: +SKIP
    25
    """
    if bc is not None:
        message = ('The keyword argument `bc` to `active_contour` has been '
                   'renamed. Use `boundary_condition=` instead. `bc` will be '
                   'removed in scikit-image v0.18.')
        warn(message, stacklevel=2)
        boundary_condition = bc
    if coordinates is None:
        message = ('The coordinates used by `active_contour` will change '
                   'from xy coordinates (transposed from image dimensions) to '
                   'rc coordinates in scikit-image 0.18. Set '
                   "`coordinates='rc'` to silence this warning. "
                   "`coordinates='xy'` will restore the old behavior until "
                   '0.18, but will stop working thereafter.')
        warn(message, category=FutureWarning, stacklevel=2)
        coordinates = 'xy'
        snake_xy = snake
    if coordinates == 'rc':
        snake_xy = snake[:, ::-1]
    max_iterations = int(max_iterations)
    if max_iterations <= 0:
        raise ValueError("max_iterations should be >0.")
    convergence_order = 10
    valid_bcs = ['periodic', 'free', 'fixed', 'free-fixed',
                 'fixed-free', 'fixed-fixed', 'free-free']
    if boundary_condition not in valid_bcs:
        raise ValueError("Invalid boundary condition.\n" +
                         "Should be one of: "+", ".join(valid_bcs)+'.')
    img = img_as_float(image)
    RGB = img.ndim == 3

    # Find edges using sobel:
    if w_edge != 0:
        if RGB:
            edge = [sobel(img[:, :, 0]), sobel(img[:, :, 1]),
                    sobel(img[:, :, 2])]
        else:
            edge = [sobel(img)]
    else:
        edge = [0]

    # Superimpose intensity and edge images:
    if RGB:
        img = w_line*np.sum(img, axis=2) \
            + w_edge*sum(edge)
    else:
        img = w_line*img + w_edge*edge[0]

    # Interpolate for smoothness:
    intp = RectBivariateSpline(np.arange(img.shape[1]),
                               np.arange(img.shape[0]),
                               img.T, kx=2, ky=2, s=0)

    x, y = snake_xy[:, 0].astype(np.float), snake_xy[:, 1].astype(np.float)
    n = len(x)
    xsave = np.empty((convergence_order, n))
    ysave = np.empty((convergence_order, n))

    # Build snake shape matrix for Euler equation
    a = np.roll(np.eye(n), -1, axis=0) + \
        np.roll(np.eye(n), -1, axis=1) - \
        2*np.eye(n)  # second order derivative, central difference
    b = np.roll(np.eye(n), -2, axis=0) + \
        np.roll(np.eye(n), -2, axis=1) - \
        4*np.roll(np.eye(n), -1, axis=0) - \
        4*np.roll(np.eye(n), -1, axis=1) + \
        6*np.eye(n)  # fourth order derivative, central difference
    A = -alpha*a + beta*b

    # Impose boundary conditions different from periodic:
    sfixed = False
    if boundary_condition.startswith('fixed'):
        A[0, :] = 0
        A[1, :] = 0
        A[1, :3] = [1, -2, 1]
        sfixed = True
    efixed = False
    if boundary_condition.endswith('fixed'):
        A[-1, :] = 0
        A[-2, :] = 0
        A[-2, -3:] = [1, -2, 1]
        efixed = True
    sfree = False
    if boundary_condition.startswith('free'):
        A[0, :] = 0
        A[0, :3] = [1, -2, 1]
        A[1, :] = 0
        A[1, :4] = [-1, 3, -3, 1]
        sfree = True
    efree = False
    if boundary_condition.endswith('free'):
        A[-1, :] = 0
        A[-1, -3:] = [1, -2, 1]
        A[-2, :] = 0
        A[-2, -4:] = [-1, 3, -3, 1]
        efree = True

    # Only one inversion is needed for implicit spline energy minimization:
    inv = np.linalg.inv(A + gamma*np.eye(n))

    # Explicit time stepping for image energy minimization:
    for i in range(max_iterations):
        fx = intp(x, y, dx=1, grid=False)
        fy = intp(x, y, dy=1, grid=False)
        if sfixed:
            fx[0] = 0
            fy[0] = 0
        if efixed:
            fx[-1] = 0
            fy[-1] = 0
        if sfree:
            fx[0] *= 2
            fy[0] *= 2
        if efree:
            fx[-1] *= 2
            fy[-1] *= 2
        xn = inv @ (gamma*x + fx)
        yn = inv @ (gamma*y + fy)

        # Movements are capped to max_px_move per iteration:
        dx = max_px_move*np.tanh(xn-x)
        dy = max_px_move*np.tanh(yn-y)
        if sfixed:
            dx[0] = 0
            dy[0] = 0
        if efixed:
            dx[-1] = 0
            dy[-1] = 0
        x += dx
        y += dy

        # Convergence criteria needs to compare to a number of previous
        # configurations since oscillations can occur.
        j = i % (convergence_order+1)
        if j < convergence_order:
            xsave[j, :] = x
            ysave[j, :] = y
        else:
            dist = np.min(np.max(np.abs(xsave-x[None, :]) +
                                 np.abs(ysave-y[None, :]), 1))
            if dist < convergence:
                break

    if coordinates == 'xy':
        return np.stack([x, y], axis=1)
    else:
        return np.stack([y, x], axis=1)

    
def visual_callback_2d(background, fig=None):
    """
    Returns a callback than can be passed as the argument `iter_callback`
    of `morphological_geodesic_active_contour` and
    `morphological_chan_vese` for visualizing the evolution
    of the levelsets. Only works for 2D images.
    
    Parameters
    ----------
    background : (M, N) array
        Image to be plotted as the background of the visual evolution.
    fig : matplotlib.figure.Figure
        Figure where results will be drawn. If not given, a new figure
        will be created.
    
    Returns
    -------
    callback : Python function
        A function that receives a levelset and updates the current plot
        accordingly. This can be passed as the `iter_callback` argument of
        `morphological_geodesic_active_contour` and
        `morphological_chan_vese`.
    
    """
    
    # Prepare the visual environment.
    if fig is None:
        fig = plt.figure()
    fig.clf()
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.imshow(background, cmap=plt.cm.gray)

    ax2 = fig.add_subplot(1, 2, 2)
    ax_u = ax2.imshow(np.zeros_like(background), vmin=0, vmax=1)
    plt.pause(0.001)

    def callback(levelset):
        
        if ax1.collections:
            del ax1.collections[0]
        ax1.contour(levelset, [0.5], colors='r')
        ax_u.set_data(levelset)
        fig.canvas.draw()
        plt.pause(0.001)

    return callback

def iter_ransac(image, sigma=3, no_iter=10, order = 'col', mxt=2500):
    
    # The plan here is to make the outliers inliers each time or summit
    
    outArray = np.zeros_like(image)
    
    #th = filters.threshold_otsu(inArray)
    
    bw = canny(image, sigma=sigma)
    
    
    inDex = np.where(bw > 0)
    
    if order =='col':       
    
        inData = np.column_stack([inDex[0], inDex[1]])
        
    if order == 'row':
        inData = np.column_stack([inDex[1], inDex[0]])
    
    for i in tqdm(range(0, no_iter)):
        
#        if orient == 'v':
        
        if order == 'col':
        
            #inData = np.column_stack([inDex[0], inDex[1]])
            
            
            model = LineModelND()
            model.estimate(inData)
        
            model_robust, inliers = ransac(inData, LineModelND, min_samples=2,
                                           residual_threshold=1, max_trials=mxt)
        
        
            outliers = np.invert(inliers)
        
            
            line_x = inData[:, 0]
            line_y = model.predict_y(line_x)
            line_y_robust = model_robust.predict_y(line_x)
        
            outArray[line_x, np.int64(np.round(line_y_robust))]=1
        
        if order == 'row':
        
#            inData = np.column_stack([inDex[1], inDex[0]])
        
        
            model = LineModelND()
            model.estimate(inData)
        
            model_robust, inliers = ransac(inData, LineModelND, min_samples=2,
                                       residual_threshold=1, max_trials=mxt)
        
        
            outliers = np.invert(inliers)
        
            
            line_x = inData[:,0]
            line_y = model.predict_y(line_x)
    
            line_y_robust = model_robust.predict_y(line_x)
            
            outArray[np.int64(np.round(line_y_robust)), line_x]=1

#    
        
        
    
        inData = inData[:,0:2][outliers==True]
        del model, model_robust, inliers, outliers
        
    
    return outArray

        

def temp_match(vector_path, raster_path, band, nodata_value=0, ind=None):
    
    """ 
    Based on polygons return template matched images
    
    
    Parameters
    ----------
    
    vector_path : string
                  input shapefile
        
    raster_path : string
                  input raster

    band : int
           an integer val eg - 2
        
    nodata_value : numerical
                   If used the no data val of the raster
    ind : int
        The feature ID to use - if used this will use one feature and rotate it 90 for the second
        
    Returns
    -------
    list of template match arrays same size as input
        
    """    

    
    rds = gdal.Open(raster_path, gdal.GA_ReadOnly)
    #assert(rds)
    rb = rds.GetRasterBand(band)
    
    
    
    rgt = rds.GetGeoTransform()

    if nodata_value:
        nodata_value = float(nodata_value)
        rb.SetNoDataValue(nodata_value)

    vds = ogr.Open(vector_path, 1)  # TODO maybe open update if we want to write stats
   #assert(vds)
    vlyr = vds.GetLayer(0)

    mem_drv = ogr.GetDriverByName('Memory')
    driver = gdal.GetDriverByName('MEM')

    # Loop through vectors
    feat = vlyr.GetNextFeature()
    features = np.arange(vlyr.GetFeatureCount())
    rejects = list()
    
    arList = []
    for label in features:

        if feat is None:
            continue
        geom = feat.geometry()

        src_offset = _bbox_to_pixel_offsets(rgt, geom)
        src_array = rb.ReadAsArray(src_offset[0], src_offset[1], src_offset[2],
                               src_offset[3])
        if src_array is None:
            src_array = rb.ReadAsArray(src_offset[0]-1, src_offset[1], src_offset[2],
                               src_offset[3])
            if src_array is None:
                rejects.append(feat.GetFID())
                continue

        # calculate new geotransform of the feature subset
        new_gt = (
        (rgt[0] + (src_offset[0] * rgt[1])),
        rgt[1],
        0.0,
        (rgt[3] + (src_offset[1] * rgt[5])),
        0.0,
        rgt[5])

            
        # Create a temporary vector layer in memory
        mem_ds = mem_drv.CreateDataSource('out')
        mem_layer = mem_ds.CreateLayer('poly', None, ogr.wkbPolygon)
        mem_layer.CreateFeature(feat.Clone())

        # Rasterize it

        rvds = driver.Create('', src_offset[2], src_offset[3], 1, gdal.GDT_Byte)
     
        rvds.SetGeoTransform(new_gt)
        rvds.SetProjection(rds.GetProjectionRef())
        rvds.SetGeoTransform(new_gt)
        gdal.RasterizeLayer(rvds, [1], mem_layer, burn_values=[1])
        rv_array = rvds.ReadAsArray()
        
        # Mask the source data array with our current feature
        # we take the logical_not to flip 0<->1 to get the correct mask effect
        # we also mask out nodata values explictly
            

        #rejects.append(feat.GetField('DN'))
        masked = np.ma.MaskedArray(
            src_array,
            mask=np.logical_or(
                src_array == nodata_value,
                np.logical_not(rv_array)
            )
        )
        
        arList.append(masked)
        feat = vlyr.GetNextFeature()
        
        
    gray = rgb2gray(io.imread(raster_path))
    
    outList = []
    if ind != None:
        nArray = arList[ind]
        rotAr = np.rot90(nArray)
        arList = [nArray, rotAr]
        
    for a in tqdm(arList):
       result = match_template(gray, a, pad_input=True)
       np.where(gray==0, 0, result)
       outList.append(result)
       

    
    return outList

def test_gabor(im, size=9,  freq=0.1, angle=None, funct='cos', plot=True, 
                  smooth=True, interp='none'):
    """ 
    Process image with gabor filter bank of specified orientation or derived from
    image positive values bounding box - implemented from numpy with more intuitive 
    params 
    
    This is the numpy based one 
    
    Parameters
    ----------
    
    inRas: string
                  input raster

    size: int
           size of in gabor kernel in pixels (ksize)
        
    freq: float
           
           
        
    angles: int
           number of angles  in gabor kernel (theta)


    """  
    
    if funct == 'cos':
        func = np.cos
    if func == 'sin':
        func = np.sin
        
    


    def genGabor(sz, omega, theta, func=func, K=np.pi):
        
        sz = (sz,sz)
        radius = (int(sz[0]/2.0), int(sz[1]/2.0))
        [x, y] = np.meshgrid(range(-radius[0], radius[0]+1), range(-radius[1], radius[1]+1))
    
        x1 = x * np.cos(theta) + y * np.sin(theta)
        y1 = -x * np.sin(theta) + y * np.cos(theta)
        
        gauss = omega**2 / (4*np.pi * K**2) * np.exp(- omega**2 / (8*K**2) * ( 4 * x1**2 + y1**2))

        sinusoid = func(omega * x1) * np.exp(K**2 / 2)

        gabor = gauss * sinusoid
        return gabor
    

    
    def deginrad(degree):
        radiant = 2*np.pi/360 * degree
        return radiant
    
    if hasattr(im, 'shape'):
        img = im
    else:
        img = rgb2gray(io.imread(im))
    
    if smooth == True:
        
        img = gaussian_filter(img, 1)
    
    #TODO add a polygon argument to make it easier....
    if angle == None:
        # here we use the orientation to get the line of crops assuming the user has
        # cropped it well
        bw = img > 0
        props = regionprops(bw*1)
        orient = props[0]['Orientation']
        angle = 90 - np.degrees(orient)

    g = genGabor(size,  freq, np.radians(angle))
           
   
    filtered_img = cv2.filter2D(img, cv2.CV_8UC3, g)
    
    theta2 = np.radians(angle+90)
    
    g2 = genGabor(size,  freq, theta2)

    filtered_img2 = cv2.filter2D(img, cv2.CV_8UC3, g2)
    
    if plot == True:
        fig=plt.figure()
        fig.add_subplot(1, 4, 1)
        plt.imshow(img)
        fig.add_subplot(1, 4, 2)
        plt.imshow(filtered_img)
        fig.add_subplot(1, 4, 3)
        plt.imshow(filtered_img2)
        fig.add_subplot(1, 4, 4)
        plt.imshow(g, interpolation=interp)
    


    return  filtered_img, filtered_img2   

def test_gabor_cv2(im, size=9,  stdv=1, angle=None, wave_length=3, eccen=1,
               phase_off=0, plot=True, smooth=True, interp='none'):
    """ 
    Process image with gabor filter bank of specified orientation or derived from
    image positive values bounding box
    
    This is the open cv based one
    
    Parameters
    ----------
    
    inRas: string
                  input raster

    size: int
           size of in gabor kernel in pixels (ksize)
        
    stdv: int
           stdv / of of gabor kernel (sigma/stdv)
           
        
    angles: int
           number of angles  in gabor kernel (theta)

    wave_length: int
           width of stripe in gabor kernel (lambda/wavelength)
           optional best to leave none and hence same as size
        
    phase_off: int
           the phase offset of the kernel      
           
    eccen: int
          the elipticity of the kernel when = 1 the gaussian envelope is circular (gamma)

    """  
    
        # ksize - size of gabor filter (n, n)
    # sigma - standard deviation of the gaussian function
    # theta - orientation of the normal to the parallel stripes
    # lambda - wavelength of the sunusoidal factor wave_length
    # gamma - spatial aspect ratio
    # psi - phase offset
    # ktype - type and range of values that each pixel in the gabor kernel can hold
    

    

    def deginrad(degree):
        radiant = 2*np.pi/360 * degree
        return radiant
    if hasattr(im, 'shape'):
        img = im
    else:
        
        img = rgb2gray(io.imread(im))
    
    if smooth == True:
        
        img = gaussian_filter(img, 1)
    
    #TODO add a polygon argument to make it easier....
    if angle == None:
        # here we use the orientation to get the line of crops assuming the user has
        # cropped it well
        bw = img > 0
        props = regionprops(bw*1)
        orient = props[0]['Orientation']
        angle = 90 - np.degrees(orient)
    
    if wave_length==None:
        wave_length = 3
    
#    if width2 == None:
#        width2 = width
#                  
    theta = deginrad(angle)   # unit circle: left: -90 deg, right: 90 deg, straight: 0 deg
    g_kernel = cv2.getGaborKernel((size, size), stdv, theta, wave_length, eccen, 
                                  phase_off, ktype=cv2.CV_32F)
    filtered_img = cv2.filter2D(img, cv2.CV_8UC3, g_kernel)
    
    theta2 = deginrad(angle+90)
    g_kernel2 = cv2.getGaborKernel((size, size), stdv, theta2, wave_length, eccen, 
                                  phase_off, ktype=cv2.CV_32F)
    filtered_img2 = cv2.filter2D(img, cv2.CV_8UC3, g_kernel2)
    
    if plot == True:
        fig=plt.figure()
        fig.add_subplot(1, 4, 1)
        plt.imshow(img)
        fig.add_subplot(1, 4, 2)
        plt.imshow(filtered_img)
        fig.add_subplot(1, 4, 3)
        plt.imshow(filtered_img2)
        fig.add_subplot(1, 4, 4)
        plt.imshow(g_kernel, interpolation=interp)
    
    #h, w = g_kernel.shape[:2]
    #g_kernel = cv2.resize(g_kernel, (3*w, 3*h), interpolation=cv2.INTER_CUBIC)
    #cv2.imshow('gabor kernel (resized)', g_kernel)
    
    
    
#    filtered_img[img==0]=0
#    filtered_img2[img==0]=0

    return  filtered_img, filtered_img2   


def accum_gabor(inRas, outRas=None, size=(9,9), stdv=1, no_angles=16, wave_length=3, eccen=1,
               phase_off=0, pltgrid=(4,4), blockproc=False):
    
    """ 
    Process with custom gabor filters and output an raster containing each 
    kernel output as a band
    
    
    Parameters
    ----------
    
    inRas: string
                  input raster
        
    outRas: string
                  output raster

    size: tuple
           size of in gabor kernel in pixels (ksize)
        
    stdv: int
           size of stdv / of of gabor kernel (sigma/stdv)
    
    no_angles: int
           number of angles  in gabor kernel (theta)

    wave_length: int
           width of stripe in gabor kernel (lambda/wavelength)  
        
    phase_off: int
           the phase offset of the kernel      
           
    eccen: int
          the elipticity of the kernel when = 1 the gaussian envelope is circular
          
    blocproc: bool
          whether to process in chunks - necessary for very large images!
    """  
    
    # ksize - size of gabor filter (n, n)
    # sigma - standard deviation of the gaussian function
    # theta - orientation of the normal to the parallel stripes
    # lambda - wavelength of the sunusoidal factor
    # gamma - spatial aspect ratio
    # psi - phase offset
    # ktype - type and range of values that each pixel in the gabor kernel can hold


    """
    Harmonic function consists of an imaginary sine function and a real cosine function. 
    Spatial frequency is inversely proportional to the wavelength of the harmonic 
    and to the standard deviation of a Gaussian kernel. 
    The bandwidth is also inversely proportional to the standard deviation.
    """
    def compute_feats(image, kernels):
        feats = np.zeros((len(kernels), 2), dtype=np.double)
        for k, kernel in enumerate(kernels):
            filtered = ndi.convolve(image, kernel, mode='wrap')
            feats[k, 0] = filtered.mean()
            feats[k, 1] = filtered.var()
        return feats
    
     
    def build_filters():
         filters = []
         
         for theta in np.arange(0, np.pi, np.pi / no_angles):
             kern = cv2.getGaborKernel(size, stdv, theta, wave_length, eccen, 
                                  phase_off, ktype=cv2.CV_32F)
             kern /= 1.5*kern.sum()
             filters.append(kern)
         return filters
    
    
    thetaz = np.arange(0, np.pi, np.pi / no_angles)
    degrees = np.rad2deg(thetaz)


    def process(img, filters):

        accum = np.zeros_like(img)
        fmgList = []

        for i, kern in enumerate(filters):
             fimg = cv2.filter2D(img, cv2.CV_8UC3, kern)
             fmgList.append(fimg)   
             np.maximum(accum, fimg, accum)
             
        return accum, fmgList
    
    
    def plot_it(fmgList, gFilters, pltgrid):
        
        """
        plt a grid of images for gab filters and outputs

        """
       
        
        fig = plt.figure(figsize=(10., 10.))
        grid = ImageGrid(fig, 111,  # similar to subplot(111)
                         nrows_ncols=pltgrid,  # creates 2x2 grid of axes
                         axes_pad=0.3, share_all=True,  # pad between axes in inch.
                         )

        for ax, im, d in zip(grid, fmgList, degrees):
            # Iterating over the grid returns the Axes.            
            ax.imshow(im)
            ax.set_title(str(d)+' degrees')
            
            ax.set_axis_off()
        
        fig1 = plt.figure(figsize=(10., 10.))
        grid1 = ImageGrid(fig1, 111,  # similar to subplot(111)
                         nrows_ncols=pltgrid,  # creates 2x2 grid of axes
                         axes_pad=0.3,  # pad between axes in inch.
                         )

        for ax1, im1, d1 in zip(grid1, gFilters, degrees):
            # Iterating over the grid returns the Axes.            
            ax1.imshow(im1)
            ax1.set_title(str(d1)+' degrees')
            ax1.set_axis_off()
        
        plt.show()
        

    gfilters = build_filters()  


                  
    inDataset = gdal.Open(inRas)
    
    if outRas != None:
        outDataset = _copy_dataset_config(inDataset, outMap = outRas,
                                         dtype = gdal.GDT_Byte, bands = no_angles)
    band = inDataset.GetRasterBand(1)
    cols = inDataset.RasterXSize
    rows = inDataset.RasterYSize
    
    bands = inDataset.RasterCount
    
    if bands > 3:
        bands = 3

    blocksizeX = 256
    blocksizeY = 256
        
    if blockproc == True and outRas != None:            
        for i in tqdm(range(0, rows, blocksizeY)):
                if i + blocksizeY < rows:
                    numRows = blocksizeY
                else:
                    numRows = rows -i
            
                for j in range(0, cols, blocksizeX):
                    if j + blocksizeX < cols:
                        numCols = blocksizeX
                    else:
                        numCols = cols - j
                    if bands == 1:
                        band1 = inDataset.GetRasterBand(band)
                        data = band1.ReadAsArray(j, i, numCols, numRows)                        
                    else:
                        data = np.zeros((blocksizeX,blocksizeX, bands))
                                                
                        for band in range(1,bands+1):
                            band1 = inDataset.GetRasterBand(band)
                            data[:,:,band-1] = band1.ReadAsArray(j, i, numCols, numRows)
                        data = color.rgb2gray(data)
                    
                    _, fmgList = process(data, gfilters)
                    
# TODO                    # [:256, :256] this will pad it if block is  bigger.....but still getting edge effect - why?
                    
                    [outDataset.GetRasterBand(k+1).WriteArray(f
                    , j,  i) for k, f in enumerate(fmgList)] 
    
                        
        outDataset.FlushCache()
        outDataset = None
                
   
    
    else:

        img  = io.imread(inRas)
        
        if len(img.shape) >1:
             img = rgb2gray(img)
            
            
            
        
        gabber, fmgList = process(img, gfilters)
        
        plot_it(fmgList, gfilters, pltgrid)
        
        if outRas != None:
        
            [outDataset.GetRasterBand(k+1).WriteArray(f) for k, f in enumerate(fmgList)]
            
            array2raster(gabber, 1, inRas, outRas[:-4]+'_comp.tif', gdal.GDT_Int32)
    return fmgList


def min_bound_rectangle(points):
    """
    Find the smallest bounding rectangle for a set of points.
    Returns a set of points representing the corners of the bounding box.
    Parameters
    ----------
    points : list
        An nx2 iterable of points
    
    Returns
    -------
    list
        an nx2 list of coordinates
    """
    points = np.asarray(points, dtype = np.float64)
    pi2 = np.pi/2.

    # get the convex hull for the points
    hull_points = points[ConvexHull(points).vertices]

    # calculate edge angles
    edges = np.zeros((len(hull_points)-1, 2))
    edges = hull_points[1:] - hull_points[:-1]

    angles = np.zeros((len(edges)))
    angles = np.arctan2(edges[:, 1], edges[:, 0])

    angles = np.abs(np.mod(angles, pi2))
    angles = np.unique(angles)

    # find rotation matrices
    # XXX both work
    rotations = np.vstack([
        np.cos(angles),
        np.cos(angles-pi2),
        np.cos(angles+pi2),
        np.cos(angles)]).T
#     rotations = np.vstack([
#         np.cos(angles),
#         -np.sin(angles),
#         np.sin(angles),
#         np.cos(angles)]).T
    rotations = rotations.reshape((-1, 2, 2))

    # apply rotations to the hull
    rot_points = np.dot(rotations, hull_points.T)

    # find the bounding points
    min_x = np.nanmin(rot_points[:, 0], axis=1)
    max_x = np.nanmax(rot_points[:, 0], axis=1)
    min_y = np.nanmin(rot_points[:, 1], axis=1)
    max_y = np.nanmax(rot_points[:, 1], axis=1)

    # find the box with the best area
    areas = (max_x - min_x) * (max_y - min_y)
    best_idx = np.argmin(areas)

    # return the best box
    x1 = max_x[best_idx]
    x2 = min_x[best_idx]
    y1 = max_y[best_idx]
    y2 = min_y[best_idx]
    r = rotations[best_idx]

    rval = list()#np.zeros((4, 2))
    rval.append(((x1,y2))) #np.dot([x1, y2], r)
    rval.append(((x2,y2)))#np.dot([x2, y2], r)
    rval.append(((x2,y1)))#np.dot([x2, y1], r)
    rval.append(((x1,y1)))#np.dot([x1, y1], r)
        
    
    return rval

def _bbox_to_pixel_offsets(rgt, geom):
    
    """ 
    Internal function to get pixel geo-locations of bbox of a polygon
    
    Parameters
    ----------
    
    rgt : array
          List of points defining polygon (?)
          
    geom : shapely.geometry
           Structure defining geometry
    
    Returns
    -------
    int
       x offset
           
    int
       y offset
           
    xcount : int
             rows of bounding box
             
    ycount : int
             columns of bounding box
    """
    
    xOrigin = rgt[0]
    yOrigin = rgt[3]
    pixelWidth = rgt[1]
    pixeleccen = rgt[5]
    ring = geom.GetGeometryRef(0)
    numpoints = ring.GetPointCount()
    pointsX = []; pointsY = []
    
    if (geom.GetGeometryName() == 'MULTIPOLYGON'):
        count = 0
        pointsX = []; pointsY = []
        for polygon in geom:
            geomInner = geom.GetGeometryRef(count)
            ring = geomInner.GetGeometryRef(0)
            numpoints = ring.GetPointCount()
            for p in range(numpoints):
                    lon, lat, z = ring.GetPoint(p)
                    pointsX.append(lon)
                    pointsY.append(lat)
            count += 1
    elif (geom.GetGeometryName() == 'POLYGON'):
        ring = geom.GetGeometryRef(0)
        numpoints = ring.GetPointCount()
        pointsX = []; pointsY = []
        for p in range(numpoints):
                lon, lat, z = ring.GetPoint(p)
                pointsX.append(lon)
                pointsY.append(lat)
            
    xmin = min(pointsX)
    xmax = max(pointsX)
    ymin = min(pointsY)
    ymax = max(pointsY)

    # Specify offset and rows and columns to read
    xoff = int((xmin - xOrigin)/pixelWidth)
    yoff = int((yOrigin - ymax)/pixelWidth)
    xcount = int((xmax - xmin)/pixelWidth)+1
    ycount = int((ymax - ymin)/pixelWidth)+1
#    originX = gt[0]
#    originY = gt[3]
#    pixel_width = gt[1]
#    pixel_eccen = gt[5]
#    x1 = int((bbox[0] - originX) / pixel_width)
#    x2 = int((bbox[1] - originX) / pixel_width) + 1
#
#    y1 = int((bbox[3] - originY) / pixel_eccen)
#    y2 = int((bbox[2] - originY) / pixel_eccen) + 1
#
#    xsize = x2 - x1
#    ysize = y2 - y1
#    return (x1, y1, xsize, ysize)
    return (xoff, yoff, xcount, ycount)  



def image_thresh(image):

#    image = rgb2gray(io.imread(im))
    
    if image.shape[0] > 4000:
        image = rescale(image, 0.5, preserve_range=True, anti_aliasing=True)
        image = np.uint8(image)
    
    def threshold(image, t):
        arr = da.from_array(image, chunks=image.shape)
        return arr > t
    
    all_thresholds = da.stack([threshold(image, t) for t in np.arange(255)])
    
    viewer = napari.view_image(image, name='input image')
    viewer.add_image(all_thresholds,
        name='thresholded', colormap='magenta', blending='additive'
    )

def colorscale(seg, prop):
    
    props = regionprops(seg)
    
    labels = np.unique(seg)
    propIm = np.zeros_like(seg, dtype=np.float64) 
    for label in labels:
        if label==0:
            continue
        propval=props[label-1][prop] 
        propIm[seg==label]=propval
    
    return propIm



def rotate_im(image, angle):
    """Rotate the image.
    
    Rotate the image such that the rotated image is enclosed inside the tightest
    rectangle. The area not occupied by the pixels of the original image is colored
    black. 
    
    Parameters
    ----------
    
    image : numpy.ndarray
        numpy image
    
    angle : float
        angle by which the image is to be rotated
    
    Returns
    -------
    
    numpy.ndarray
        Rotated Image
    
    """
    # grab the dimensions of the image and then determine the
    # centre
    (h, w) = image.shape[:2]
    (cX, cY) = (w // 2, h // 2)

    # grab the rotation matrix (applying the negative of the
    # angle to rotate clockwise), then grab the sine and cosine
    # (i.e., the rotation components of the matrix)
    M = cv2.getRotationMatrix2D((cX, cY), angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])

    # compute the new bounding dimensions of the image
    nW = int((h * sin) + (w * cos))
    nH = int((h * cos) + (w * sin))

    # adjust the rotation matrix to take into account translation
    M[0, 2] += (nW / 2) - cX
    M[1, 2] += (nH / 2) - cY

    # perform the actual rotation and return the image
    image = cv2.warpAffine(image, M, (nW, nH))

#    image = cv2.resize(image, (w,h))
    return image


def get_corners(bboxes):
    
    """Get corners of bounding boxes
    
    Parameters
    ----------
    
    bboxes: numpy.ndarray
        Numpy array containing bounding boxes of shape `N X 4` where N is the 
        number of bounding boxes and the bounding boxes are represented in the
        format `x1 y1 x2 y2`
    
    returns
    -------
    
    numpy.ndarray
        Numpy array of shape `N x 8` containing N bounding boxes each described by their 
        corner co-ordinates `x1 y1 x2 y2 x3 y3 x4 y4`      
        
    """
    width = (bboxes[:,2] - bboxes[:,0]).reshape(-1,1)
    height = (bboxes[:,3] - bboxes[:,1]).reshape(-1,1)
    
    x1 = bboxes[:,0].reshape(-1,1)
    y1 = bboxes[:,1].reshape(-1,1)
    
    x2 = x1 + width
    y2 = y1 
    
    x3 = x1
    y3 = y1 + height
    
    x4 = bboxes[:,2].reshape(-1,1)
    y4 = bboxes[:,3].reshape(-1,1)
    
    corners = np.hstack((x1,y1,x2,y2,x3,y3,x4,y4))
    
    return corners


def rotate_box(corners,angle,  cx, cy, h, w):
    
    """Rotate the bounding box.
    
    
    Parameters
    ----------
    
    corners : numpy.ndarray
        Numpy array of shape `N x 8` containing N bounding boxes each described by their 
        corner co-ordinates `x1 y1 x2 y2 x3 y3 x4 y4`
    
    angle : float
        angle by which the image is to be rotated
        
    cx : int
        x coordinate of the center of image (about which the box will be rotated)
        
    cy : int
        y coordinate of the center of image (about which the box will be rotated)
        
    h : int 
        height of the image
        
    w : int 
        width of the image
    
    Returns
    -------
    
    numpy.ndarray
        Numpy array of shape `N x 8` containing N rotated bounding boxes each described by their 
        corner co-ordinates `x1 y1 x2 y2 x3 y3 x4 y4`
    """

    corners = corners.reshape(-1,2)
    corners = np.hstack((corners, np.ones((corners.shape[0],1), dtype = type(corners[0][0]))))
    
    M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    
    
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    
    nW = int((h * sin) + (w * cos))
    nH = int((h * cos) + (w * sin))
    # adjust the rotation matrix to take into account translation
    M[0, 2] += (nW / 2) - cx
    M[1, 2] += (nH / 2) - cy
    # Prepare the vector to be transformed
    calculated = np.dot(M,corners.T).T
    
    calculated = calculated.reshape(-1,8)
    
    return calculated

def get_enclosing_box(corners):
    """Get an enclosing box for ratated corners of a bounding box
    
    Parameters
    ----------
    
    corners : numpy.ndarray
        Numpy array of shape `N x 8` containing N bounding boxes each described by their 
        corner co-ordinates `x1 y1 x2 y2 x3 y3 x4 y4`  
    
    Returns 
    -------
    
    numpy.ndarray
        Numpy array containing enclosing bounding boxes of shape `N X 4` where N is the 
        number of bounding boxes and the bounding boxes are represented in the
        format `x1 y1 x2 y2`
        
    """
    x_ = corners[:,[0,2,4,6]]
    y_ = corners[:,[1,3,5,7]]
    
    xmin = np.min(x_,1).reshape(-1,1)
    ymin = np.min(y_,1).reshape(-1,1)
    xmax = np.max(x_,1).reshape(-1,1)
    ymax = np.max(y_,1).reshape(-1,1)
    
    final = np.hstack((xmin, ymin, xmax, ymax,corners[:,8:]))
    
    return final

def spinim(self, img, bboxes):

    angle = random.uniform(*self.angle)

    w,h = img.shape[1], img.shape[0]
    cx, cy = w//2, h//2

    img = rotate_im(img, angle)

    corners = get_corners(bboxes)

    corners = np.hstack((corners, bboxes[:,4:]))


    corners[:,:8] = rotate_box(corners[:,:8], angle, cx, cy, h, w)

    new_bbox = get_enclosing_box(corners)


    scale_factor_x = img.shape[1] / w

    scale_factor_y = img.shape[0] / h

    img = cv2.resize(img, (w,h))

    new_bbox[:,:4] /= [scale_factor_x, scale_factor_y, scale_factor_x, scale_factor_y] 

    bboxes  = new_bbox

    bboxes = clip_box(bboxes, [0,0,w, h], 0.25)

    return img, bboxes

def otbMeanshift(inputImage, radius, rangeF, minSize, outShape):
    """ 
    OTB meanshift by calling the otb command line
    Written for convenience and due to otb python api being rather verbose 
    
    Notes:
    -----------        
    There is a maximum size for the .shp format otb doesn't seem to
    want to move beyond (2gb), so enormous rasters may need to be sub
    divided
        
    You will need to install OTB etc seperately
                
        
    Parameters
    -----------    
     
    inputImage : string
                 the input image 
        
    radius : int
             the kernel radius
        
    rangeF : int
             the kernel range
        
    minSize : int
              minimum segment size
        
    outShape : string
               the ouput shapefile

    
    """
    # Yes it is possible to do this with the otb python api, but it is way more
    # verbose, hence using the command line
    # the long winded version is greyed out as takes far too long to process
    print('segmenting image.... could be a little while!')
#    cmd1 = ('otbcli_MeanShiftSmoothing -in '+inputImage+ '
#            '-fout MeanShift_FilterOutput.tif -foutpos '
#            'MeanShift_SpatialOutput.tif -spatialr 16 -ranger 16 ' 
#            '-thres 0.1 -maxiter 100')
#    cmd2 = ('otbcli_LSMSSegmentation -in smooth.tif -inpos position.tif ' 
#            '-out segmentation.tif -ranger '+rangeF+' -spatialr '+radius+' 
#            ' -minsize '+minSize+'
#            ' -tilesizex 500 -tilesizey 500')
#    cmd3 = ('otbcli_LSMSSmallRegionsMerging -in smooth.tif '
#            '-inseg segmentation.tif -out merged.tif -minsize 20'
#            '-tilesizex 500 -tilesizey 500')
#    cmd4 = ('otbcli_LSMSVectorization -in avions.tif -inseg merged.tif '
#            '-out vector.shp -tilesizex 500 -tilesizey 500')
            
    cmd1 = ['otbcli_Segmentation', '-in', str(inputImage), '-filter meanshift',
            '-filter.meanshift.spatialr', str(radius),
            '-filter.meanshift.ranger', str(rangeF), 
            '-filter.meanshift.minsize', str(minSize), '-mode', 'vector',
            '-mode.vector.out', outShape]
    cmd1out = subprocess.check_output(cmd1)
    print(cmd1out)
#    print('filtering done')
#    os.system(cmd2)
#    print('raster seg done')
#    os.system(cmd3)
#    print('region merge done')
#    os.system(cmd4)
    print('vectorisation done - process complete - phew!')
#    output = subprocess.Popen([cmd], stdout=subprocess.PIPE).communicate()[0]
#    print(output)