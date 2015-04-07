from .. import Device
from .ad_base import AD_Camera
from .ad_fileplugin import AD_FilePlugin

class AD_ImagePlugin(Device):
    """
    Wrapper for AreaDetector Image Plugin
    """
    
    attrs = ('ArrayData', 'UniqueId_RBV', 'NDimensions_RBV',
             'ArraySize0_RBV', 'ArraySize1_RBV', 'ArraySize2_RBV',
             'ColorMode_RBV')

    _nonpvs = ('_prefix', '_pvs', '_delim')

    def __init__(self, prefix):
        Device.__init__(self, prefix, delim='', mutable=False,
                        attrs=self.attrs)

    def ensure_value(self, attr, value, wait=False):
        """ensures that an attribute with an associated _RBV value is
        set to the specifed value
        """
        rbv_attr = "%s_RBV" % attr
        if rbv_attr not in self._pvs:
            return self._pvs[attr].put(value, wait=wait)

        if  self._pvs[rbv_attr].get(as_string=True) != value:
            self._pvs[attr].put(value, wait=wait)


class AD_Image(object):
    """
    AreaDetector Camera ('cam1') + Image ('image1') +  methods, 
    including adding a file plugin

    """

    def __init__(self, prefix, cam='cam1', image='image1',
                 fileplugin=None):
        if prefix.endswith(':'):    prefix = prefix[:-1]
        if cam.endswith(':'):       cam = cam[:-1]
        if image.endswith(':'):     image = image[:-1]
        
        self.camera = AD_Camera("%s:%s:" % (prefix, cam))
        self.image  = AD_ImagePlugin("%s:%s:" % (prefix, image))
        self.filepluging = None
        if fileplugin is not None:
            if fileplugin.endswith(':'):
                fileplugin = fileplugin[:-1]
            self.fileplugin = AD_FilePlugin("%s:%s:" % (prefix, fileplugin))

    def get_image(self):
        "return image, as correctly shaped and cast numpy array"

        print(" Get Image")
        for attr in ('ColorMode', 'DataType_RBV', 'SizeX_RBV', 'SizeY_RBV'):
            print("   %s: %s" % (attr, self.camera.get(attr, as_string=True)))

        for attr in ('NDimensions_RBV', 'ArraySize0_RBV', 'ArraySize1_RBV',
                     'ArraySize2_RBV', 'ColorMode_RBV'):
            print("   %s: %s" % (attr, self.image.get(attr, as_string=True)))
            
        return None
    
