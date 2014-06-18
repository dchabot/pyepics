#!/usr/bin/python
import sys
import time
import numpy
import epics
try:
    from collections import OrderedDict
except:
    from ordereddict import OrderedDict

if sys.version[0] == '2':
    from ConfigParser import  ConfigParser
elif sys.version[0] == '3':
    from configparser import  ConfigParser

MAX_ROIS = 32
class DXP(epics.Device):
    _attrs = ('PreampGain','MaxEnergy','ADCPercentRule','BaselineCutPercent',
              'BaselineThreshold','BaselineFilterLength','BaselineCutEnable',
              'InputCountRate', 'OutputCountRate',
              'GapTime','PeakingTime','EnergyThreshold','MaxWidth',
              'PresetMode', 'TriggerPeakingTime',
              'TriggerGapTime','TriggerThreshold')

    def __init__(self,prefix,mca=1):
        self._prefix = "%sdxp%i" % (prefix, mca)
        epics.Device.__init__(self, self._prefix, delim=':')
        epics.poll()

class MCA(epics.Device):
    _attrs =('CALO','CALS','CALQ','TTH', 'EGU', 'VAL',
             'PRTM', 'PLTM', 'ACT', 'RTIM', 'STIM',
             'ACQG', 'NUSE','PCT', 'PTCL',
             'DWEL', 'CHAS', 'PSCL', 'SEQ',
             'ERTM', 'ELTM', 'IDTIM')
    _nonpvs = ('_prefix', '_pvs', '_delim', '_npts')

    def __init__(self, prefix, mca=None, nrois=4):
        self._prefix = prefix
        self._npts = None
        if isinstance(mca, int):
            self._prefix = "%smca%i" % (prefix, mca)
        if nrois is None: nrois = MAX_ROIS
        attrs = list(self._attrs)
        for i in range(nrois):
            attrs.extend(['R%iNM' %i, 'R%iLO'%i,'R%iHI'%i])
        epics.Device.__init__(self,self._prefix, delim='.',
                              attrs= attrs)
        epics.poll()

    def get_rois(self, nrois=None):
        rois = OrderedDict()
        if nrois is None:
            nrois = MAX_ROIS
        for i in range(nrois):
            name = self.get('R%iNM'%i).strip()
            if name is  None or len(name.strip()) < 1:
                break
            rois[name] = (self.get('R%iLO'%i), self.get('R%iHI'%i))
        return rois

    def sorted_rois(self, rois):
        return sorted(rois.items(), cmp=lambda a,b: a[1][0] - b[1][0])

    def del_roi(self, roiname):
        rois = self.get_rois()
        if roiname in rois:
            rois.pop(roiname)
            self.set_rois(rois)

    def add_roi(self, roiname, lo=-1, hi=-1, calib=None):
        if lo < 0 or hi <0:
            return
        rois = self.get_rois()
        roiname = roiname.strip()
        rois[roiname] = (lo, hi)
        self.set_rois(rois, calib=calib)

    def set_rois(self, rois, calib=None):
        """set all rois, with optional calibration that those
        ROIs correspond to (if they have a different energy 
        calibration)

        That is, ROIs can be copied by energy from one mca to 
        another with:

           rois  = mca1.get_rois()
           calib = mca1.get_calib()
           mca2.set_rois(rois, calib=calib)
        """
        
        offset, scale = 0.0, 1.0
        if calib is not None:
            off, slope, quad = self.get_calib()
            offset = calib[0] - off
            scale  = calib[1] / slope

        for iroi, data in enumerate(self.sorted_rois(rois)):
            name, vals = data 
            name = name.strip()
            lo, hi = vals
            self.put('R%iNM'%iroi, name) 
            self.put('R%iLO'%iroi, round(offset + scale*lo))
            self.put('R%iHI'%iroi, round(offset + scale*hi))

    def clear_rois(self, nrois=None):
        if nrois is None:
            nrois = MAX_ROIS
        for i in range(nrois):
            self.put('R%iNM'%i, '')
            self.put('R%iLO'%i, -1)
            self.put('R%iHI'%i, -1)

    def get_calib(self):
        return [self.get(i) for i in ('CALO','CALS','CALQ')]

    def get_energy(self):
        if self._npts is None:
            self._npts = len(self.get('VAL'))
        
        en = numpy.arange(self._npts, dtype='f8')
        cal = self.get_calib()
        return cal[0] + en*(cal[1] + en*cal[2])
    

class MultiXMAP(epics.Device):
    """
    multi-Channel XMAP DXP device
    """

    attrs = ['PresetReal','Dwell','Acquiring', 'EraseStart','StopAll',
             'PresetMode', 'PixelsPerBuffer_RBV', 'NextPixel',
             'PixelsPerRun', 'Apply', 'AutoApply', 'CollectMode',
             'SyncCount', 'BufferSize_RBV']

    pathattrs = ('FilePath', 'FileTemplate', 'FileWriteMode',
                 'FileName', 'FileNumber', 'FullFileName_RBV',
                 'Capture',  'NumCapture', 'WriteFile_RBV',
                 'AutoSave', 'EnableCallbacks',  'ArraySize0_RBV',
                 'FileTemplate_RBV', 'FileName_RBV', 'AutoIncrement')

    _nonpvs  = ('_prefix', '_pvs', '_delim', 'filesaver',
                'pathattrs', '_nonpvs', 'nmca', 'dxps', 'mcas')

    def __init__(self, prefix, filesaver='netCDF1:',nmca=4):
        self.filesaver = filesaver
        self._prefix = prefix
        self.nmca   = nmca

        self.dxps = [DXP(prefix, mca=i+1) for i in range(nmca)]
        self.mcas = [MCA(prefix, mca=i+1) for i in range(nmca)]

        epics.Device.__init__(self, prefix, attrs=self.attrs,
                              delim='', mutable=True)
        for p in self.pathattrs:
            pvname = '%s%s%s' % (prefix, filesaver, p)
            self.add_pv(pvname, attr=p)

    def get_calib(self):
        return [m.get_calib() for m in self.mcas]

    def get_rois(self):
        return [m.get_rois() for m in self.mcas]

    def roi_calib_info(self):
        buff = ['[rois]']
        add = buff.append
        roidat = self.get_rois()

        for i, k in enumerate(roidat[0].keys()):
            s = [list(roidat[m][k]) for m in range(self.nmca)]
            rd = repr(s).replace('],', '').replace('[', '').replace(']','').replace(',','')
            add("ROI%2.2i = %s | %s" % (i,k,rd))

        caldat = numpy.array(self.get_calib())
        add('[calibration]')
        add("OFFSET = %s " % (' '.join(["%.7g" % i for i in caldat[:, 0]])))
        add("SLOPE  = %s " % (' '.join(["%.7g" % i for i in caldat[:, 1]])))
        add("QUAD   = %s " % (' '.join(["%.7g" % i for i in caldat[:, 2]])))

        add('[dxp]')
        for a in self.dxps[0]._attrs:
            vals = [str(dxp.get(a, as_string=True)).replace(' ','_') for dxp in self.dxps]
            add("%s = %s" % (a, ' '.join(vals)))
        return buff

    def restore_rois(self, roifile):
        """restore ROI setting from ROI.dat file"""
        cp =  ConfigParser()
        cp.read(roifile)
        rois = {}
        for a in cp.options('rois'):
            if a.lower().startswith('roi'):
                name, dat = cp.get('rois',a).split('|')
                lims = [int(i) for i in dat.split()]
                rois[name] = (lims[0], lims[1])
        self.mcas[0].set_rois(rois)
        cal0 = self.mcas[0].get_calib()
        for mca in self.mcas[1:]:
            mca.set_rois(rois, calib = cal0)
    
    def Write_CurrentConfig(self, filename=None):
        buff = []
        add = buff.append
        add('#Multi-Element xMAP Settings saved: %s' % time.ctime())
        add('[general]')
        add('prefix= %s' % self._prefix)
        add('nmcas = %i' % self.nmca)
        add('filesaver= %s' % self.filesaver)
        d.add('starting roi....')
        buff.extend( self.roi_calib_info() )

        d.add('wrote roi / calib / dxp')

        buff = '\n'.join(buff)
        if filename is not None:
            fh = open(filename,'w')
            fh.write(buff)
            fh.close()
        d.add('wrote file')
        # d.show()
        return buff

    def start(self):
        "Start Struck"
        self.EraseStart = 1

        if self.Acquiring == 0:
            epics.poll()
            self.EraseStart = 1
        return self.EraseStart

    def stop(self):
        "Stop Struck Collection"
        self.StopAll = 1
        return self.StopAll

    def next_pixel(self):
        "Advance to Next Pixel:"
        self.NextPixel = 1
        return self.NextPixel

    def finish_pixels(self, timeout=2):
        "Advance to Next Pixel until CurrentPixel == PixelsPerRun"
        pprun = self.PixelsPerRun
        cur   = self.dxps[0].get('CurrentPixel')
        t0 = time.time()
        while cur < pprun and time.time()-t0 < timeout:
            time.sleep(0.1)
            pprun = self.PixelsPerRun
            cur   = self.dxps[0].get('CurrentPixel')
        ok = cur >= pprun
        if not ok:
            print('XMAP needs to finish pixels ', cur, ' / ' , pprun)
            for i in range(pprun-cur):
                self.next_pixel()
                time.sleep(0.10)
            self.FileCaptureOff()
        return ok, pprun-cur


    def readmca(self,n=1):
        "Read a Struck MCA"
        return self.get('mca%i' % n)

    def SCAMode(self):
        "put XMAP in SCA mapping mode"
        self.CollectMode = 2

    def SpectraMode(self):
        "put XMAP in MCA spectra mode"
        self.stop()
        self.CollectMode = 0
        self.PresetMode = 0
        # wait until BufferSize is ready
        buffsize = -1
        t0 = time.time()
        while time.time() - t0 < 5:
            self.CollectMode = 0
            time.sleep(0.05)
            if self.BufferSize_RBV < 16384:
                break

    def MCAMode(self, filename=None, filenumber=None, npulses=11):
        "put XMAP in MCA mapping mode"
        self.AutoApply = 1
        self.stop()
        self.PresetMode = 0
        self.setFileWriteMode(2)
        if npulses < 2:
            npulses = 2
        self.CollectMode = 1
        self.PixelsPerRun = npulses

        # First, make sure ArraySize0_RBV for the netcdf plugin
        # is the correct value
        self.FileCaptureOff()
        self.start()
        f_size = -1
        t0 = time.time()
        while (f_size < 16384) and time.time()-t0 < 10:
            for i in range(5):
                time.sleep(0.1)
                self.NextPixel = 1
                f_size = self.fileGet('ArraySize0_RBV')
                if f_size > 16384:
                    break
        #
        self.PixelsPerRun = npulses
        self.SyncCount =  1

        self.setFileNumber(filenumber)
        if filename is not None:
            self.setFileName(filename)

        # wait until BufferSize is ready
        self.Apply = 1
        self.CollectMode = 1
        self.PixelsPerRun = npulses
        time.sleep(0.50)
        t0 = time.time()
        while time.time() - t0 < 10:
            time.sleep(0.25)
            if self.BufferSize_RBV > 16384:
                break

        # set expected number of buffers to put in a single file
        ppbuff = self.PixelsPerBuffer_RBV
        time.sleep(0.25)
        if ppbuff is None:
            ppbuff = 124
        self.setFileNumCapture(1 + (npulses-1)/ppbuff)
        f_buffsize = -1
        t0 = time.time()
        while time.time()- t0 < 5:
            time.sleep(0.1)
            f_buffsize = self.fileGet('ArraySize0_RBV')
            if self.BufferSize_RBV == f_buffsize:
                break

        time.sleep(0.5)
        return

    def filePut(self,attr, value, **kw):
        return self.put("%s%s" % (self.filesaver, attr), value, **kw)

    def fileGet(self, attr, **kw):
        return self.get("%s%s" % (self.filesaver, attr), **kw)

    def setFilePath(self, pathname):
        return self.filePut('FilePath', pathname)

    def setFileTemplate(self, fmt):
        return self.filePut('FileTemplate', fmt)

    def setFileWriteMode(self, mode):
        return self.filePut('FileWriteMode', mode)

    def setFileName(self, fname):
        return self.filePut('FileName', fname)

    def nextFileNumber(self):
        self.setFileNumber(1+self.fileGet('FileNumber'))

    def setFileNumber(self, fnum=None):
        if fnum is None:
            self.filePut('AutoIncrement', 1)
        else:
            self.filePut('AutoIncrement', 0)
            return self.filePut('FileNumber',fnum)

    def getLastFileName(self):
        return self.fileGet('FullFileName_RBV',as_string=True)

    def FileCaptureOn(self):
        return self.filePut('Capture', 1)

    def FileCaptureOff(self):
        return self.filePut('Capture', 0)

    def setFileNumCapture(self,n):
        return self.filePut('NumCapture', n)

    def FileWriteComplete(self):
        return (0==self.fileGet('WriteFile_RBV') )

    def getFileTemplate(self):
        return self.fileGet('FileTemplate_RBV',as_string=True)

    def getFileName(self):
        return self.fileGet('FileName_RBV',as_string=True)

    def getFileNumber(self):
        return self.fileGet('FileNumber_RBV')

    def getFilePath(self):
        return self.fileGet('FilePath_RBV',as_string=True)

    def getFileNameByIndex(self,index):
        return self.getFileTemplate() % (self.getFilePath(), self.getFileName(), index)

