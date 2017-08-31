.. _quickstart:

Quickstart
==========


Notes
---------

Be sure to replace the paths with paths to your own imagery/polygons!


Training and model creation
---------------------------

The following simple example uses the learning module to read in training from a shapefile and associated raster, then exhaustively grid search the model based on a default range of parameters. It is also possible to pass sklearn parameteter dicts to the create_model function. 

Bear in mind a large amount of training data and a lot of paramter combinations results in many model fits and lengthy grid search time! 

.. code-block:: python
   
   # Import the module required
   from geospatial_learn import learning
   
   # collect some training data
   trainShape = 'path/to/my/trainingShp.shp'
   inRas = 'path/to/my/rasterFile.shp'	

   # training collection, returning any rejects (invalid geometry - rej)
   # the 'Class' string is the title of the training label field attribute
   training, rej = learning.get_training(trainShape, inRas, 8, 'Class')
   
   # path to my model	
   model = 'path/to/my/model.gz'


   # 	
   results = learning.create_model(training, model, clf='rf', cv=3,
                                cores = 8, strat=True)
   
Classification 
---------------

The following code uses the learning module to classify an image based on the model made in the code above. 


.. code-block:: python

   from geospatial_learn import learning

   # no of bands in raster
   bands = 8

   # path to output map
   outMap = 'path/to/my/rasterFile'

   learning.classify_pixel_bloc(model, inRas, bands, outMap,  blocksize=256)


Polygon processing
------------------

Add attributes to a shapefile - perhaps with a view to classifying them later. 

The following calculates some geometric properties and pixel based statistics using functions form the shape module. 

.. code-block:: python

   from geospatial_learn.shape import shape_props, zonal_stats
   
   # path to polygon
   segShape = 'path/to/my/segmentShp.shp'
   
   # function to write 
   
   # Property of interest	
   prop = 'Eccentricity'

   # function
   shape_props(inShape, prop, inRas=None,  label_field='ID')

   # variables for function
   band = 1
   inRas = 'pth/to/myraster.tif'
   bandname = 'Blue'

   # function
   zonal_stats(segShape, inRas, band, bandname, stat = 'mean',
                write_stat=None, nodata_value=None)


Sentinel 2 data
---------------

The following code will stack a set of Sentinel 2 (S2) bands into a single raster. The code uses the module 'geodata', which has a range of functions for manipulating raster data.
I have used a genuine S2 path here hence the extreme length of the string!

The function automatically names the stacked raster and saves it in the granule folder. 


.. code-block:: python

   path = '/path/to/S2A_MSIL1C_20161223T075332_N0204_R135_T36MYE_20161223T080853/S2A_MSIL2A_20161223T075332_N0204_R135_T36MYE_20161223T080853.SAFE/GRANULE/L2A_T36MYE_A007854_20161223T080853/'	

   outputPth = geodata.stack_S2(path)

	