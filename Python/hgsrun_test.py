'''
Created on Aug 11, 2016

Unittests for hgsrun components.

@author: Andre R. Erler, GPL v3
'''

import unittest
import numpy as np
import os, sys, gc, shutil
import subprocess
from subprocess import STDOUT

# WindowsError is not defined on Linux - need a dummy
try: 
    WindowsError
except NameError:
    WindowsError = None

# import modules to be tested
from hgsrun.hgs_setup import Grok, GrokError, HGS, HGSError
from hgsrun.hgs_ensemble import EnsHGS, EnsembleError

# work directory settings ("global" variable)
data_root = os.getenv('DATA_ROOT', '')
# test folder either RAM disk or data directory
RAM = bool(os.getenv('RAMDISK', '')) # whether or not to use a RAM disk
# RAM = WindowsError is None # RAMDISK may not exist on Windows...
loverwrite = RAM # copying folders on disk takes long...

# N.B.: the environment variable RAMDISK contains the path to the RAM disk
workdir = os.getenv('RAMDISK', '') if RAM else '{:s}/test/'.format(data_root)
if not os.path.isdir(workdir): raise IOError(workdir)
# other settings
NP = 2 # for parallel tests
ldebug = False # additional debug output
# lbin = True # execute binaries to test runner methods
lbin = False # don't execute binaries (takes very long)


## tests for Grok class
class GrokTest(unittest.TestCase):  
  # some Grok test data
  hgs_template = data_root+'/HGS/Templates/GRW-test/' 
  hgs_testcase = 'grw_omafra' # name of test project (for file names)
#   hgs_template = data_root+'/HGS/Templates/GRW-V2/' 
#   hgs_testcase = 'GRC' # name of test project (for file names)
  test_data    = data_root+'/HGS/Templates/input/clim/climate_forcing/'
  test_prefix  = 'grw2' # pefix for climate input
  lvalidate    = False # validate input data
  rundir       = '{}/grok_test/'.format(workdir,) # test folder
  grok_bin     = 'grok_premium.x' # Grok executable
   
  def setUp(self):
    ''' initialize a Grok instance '''
    if not os.path.isdir(self.hgs_template): 
      raise IOError("HGS Template for testing not found:\n '{}'".format(self.hgs_template))
    if os.path.isdir(self.rundir):
      subprocess.call(['rm','-r',self.rundir],) # ignore errors... somehow this is unreliable on Windows...
    os.mkdir(self.rundir) # don't try to create if remove failed...
    # grok test files
    self.grok_input  = '{}/{}.grok'.format(self.hgs_template,self.hgs_testcase)
    self.grok_output = '{}/{}.grok'.format(self.rundir,self.hgs_testcase)
    # some grok settings
    self.runtime = 5*365*24*60*60 # two years in seconds
    self.input_interval = 'monthly'
    self.input_mode = 'periodic'
    # create Grok instance
    self.grok = Grok(rundir=self.rundir, project=self.hgs_testcase, runtime=self.runtime,
                     input_mode=self.input_mode, input_interval=self.input_interval)
    # load a config file from template
    if not os.path.isfile(self.grok_input):
      raise IOError("Grok configuration file for testing not found:\n '{}'".format(self.grok_input))
    self.grok.readConfig(folder=self.hgs_template)
    if self.grok.runtime is not None: # need to set runtime manually here 
      self.grok.setRuntime(runtime=self.grok.runtime)
    assert isinstance(self.grok._lines, list), self.grok._lines
      
  def tearDown(self):
    ''' clean up '''
    self.grok.writeConfig()
    del self.grok
    gc.collect()
 
  def testClass(self):
    ''' test instantiation of class '''    
    # instantiation done in self.setUp()
    assert self.grok.rundir, self.grok.rundir
    assert os.path.isdir(self.grok.rundir), self.grok.rundir
    
  def testInputLists(self):
    ''' test writing of input list files with climate forcings '''
    grok = self.grok  
    # write lists for fictional scenario
    grok.generateInputLists(input_vars='WRFPET', input_prefix=self.test_prefix, pet_folder=self.test_data,
                            input_folder=self.test_data, lvalidate=self.lvalidate,)
    # convert config file list into string and verify
    output = ''.join(grok._lines) # don't need newlines 
    assert 'precip.inc' in output
    assert 'pet.inc' in output    
    
  def testRestart(self):
    ''' load config file from rundir and modify restart time etc. '''
    grok = self.grok
    # write to rundir
    grok.writeConfig() 
    assert os.path.isfile(self.grok_output), self.grok_output
    old_times = grok.getParam('output times', dtype='float', llist=True)
    grok._lines = None # delete already loaded file contents
    # create fake output files for restart
    for i in range(5):
        pm_file = '{}/{}'.format(grok.rundir,grok.pm_files.format(IDX=i+1))
        open(pm_file,'w').close()
        olf_file = '{}/{}'.format(grok.rundir,grok.olf_files.format(IDX=i+1))
        open(olf_file,'w').close()
    # read from template
    grok.readConfig(folder=self.rundir)
    assert isinstance(grok._lines, list), grok._lines
    new_times = grok.getParam('output times', dtype='float', llist=None)
    assert all([old == new for old,new in zip(old_times,new_times)]), old_times
    assert all(np.diff(new_times) > 0), np.diff(new_times)
    # apply modifications for restart
    restart_file = grok.rewriteRestart()
    assert os.path.isfile(restart_file), restart_file
    # write modified file to rundir
    grok.writeConfig()
    assert os.path.isfile(self.grok_output), self.grok_output
    # verify grok file
    grok._lines = None # delete already loaded file contents
    grok.readConfig(folder=self.rundir)
    assert isinstance(grok._lines, list), grok._lines
    new_times = grok.getParam('output times', dtype='float', llist=None)
    assert len(new_times) == max(len(old_times)-5,0), (len(new_times),len(old_times))
    assert all([old == new for old,new in zip(old_times[5:],new_times)]), old_times
    assert all(np.diff(new_times) > 0), np.diff(new_times)
    
  def testRunGrok(self):
    ''' test the Grok runner command (will fail, because other inputs are missing) '''
    grok = self.grok  
    exe = '{}/{}'.format(self.hgs_template,self.grok_bin)
    logfile = '{}/log.grok'.format(grok.rundir)
    # run Grok
    if not os.path.isfile(exe): raise IOError(exe)
    try: 
      ec = grok.runGrok(executable=exe, logfile=logfile, ldryrun=not lbin)
      if not lbin: ec = 1 # because the test should fail...
    except GrokError: ec = 1
    # check output
    batchpfx = '{}/batch.pfx'.format(self.rundir)
    assert os.path.isfile(batchpfx), batchpfx
    assert os.path.isfile(logfile), logfile
    assert ec > 0, ec
    
  def testSetTime(self):
    ''' test setting the run time variable in Grok config file '''
    grok = self.grok
    time = 24*60*60 # in seconds, i.e. one day
    # set run time
    ec = grok.setRuntime(time)
    # test
    assert grok.runtime == time and ec == 0
    # test output times
    outtimes = grok.getParam('output times', dtype='float', llist=None)
    assert all(np.diff(outtimes) > 0), outtimes
    lenot = np.sum(grok.output_interval)-len(grok.output_interval)+1
    assert len(outtimes) == lenot, grok.output_interval  
    # convert config file list into string and verify
    output = ''.join(grok._lines) # don't need newlines 
    #print(output)
    assert '{:e}'.format(time) in output, '{:e}'.format(time)
    
  def testWrite(self):
    ''' load config file from template and write to rundir (on disk) '''
    grok = self.grok
    grok._lines = None # delete already loaded file contents
    # read from template
    assert os.path.isfile(self.grok_input), self.grok_input 
    grok.readConfig(folder=self.hgs_template)
    assert isinstance(grok._lines, list), grok._lines
    # write to rundir
    grok.writeConfig() 
    assert os.path.isfile(self.grok_output), self.grok_output
    

## tests for HGS class
class HGSTest(GrokTest):  
  # some HGS test data
  lvalidate    = True # validate input data
  rundir       = '{}/hgs_test/'.format(workdir,) # test folder
  hgs_bin      = 'hgs_premium.x' # HGS executable
  hgsdir       = os.getenv('HGSDIR',) # HGS license file
   
  def setUp(self):
    ''' initialize an HGS intance '''
    if not os.path.isdir(self.hgs_template): 
      raise IOError("HGS Template for testing not found:\n '{}'".format(self.hgs_template))
    if os.path.isdir(self.rundir):
      subprocess.call(['rm','-r',self.rundir],) # ignore errors... somehow this is unreliable on Windows...
    os.mkdir(self.rundir) # don't try to create if remove failed...
    # grok test files
    self.grok_input  = '{}/{}.grok'.format(self.hgs_template,self.hgs_testcase)
    self.grok_output = '{}/{}.grok'.format(self.rundir,self.hgs_testcase)
    # some grok settings
    self.runtime = 5*365*24*60*60 # five years in seconds
    self.input_interval = 'monthly'
#     self.input_mode = 'periodic'
    self.input_mode = 'quasi-transient'
    input_folder = data_root+'/HGS/Templates/input/timeseries/climate_forcing/'
    pet_folder = data_root+'/HGS/Templates/input/clim/climate_forcing/'
    # HGS settings
    self.NP = NP
    # create Grok instance
    self.hgs = HGS(rundir=self.rundir, project=self.hgs_testcase, runtime=self.runtime,
                   input_mode=self.input_mode, input_interval=self.input_interval, 
                   input_prefix=self.test_prefix, input_folder=input_folder, pet_folder=pet_folder,
                   template_folder=self.hgs_template, NP=self.NP)
    self.grok = self.hgs
    # load a config file from template
    if not os.path.isfile(self.grok_input):
      raise IOError("Grok configuration file for testing not found:\n '{}'".format(self.grok_input))
    self.grok.readConfig(folder=self.hgs_template)
    assert isinstance(self.hgs._lines, list), self.hgs._lines

  def tearDown(self):
    ''' clean up '''
    self.grok.writeConfig()
    del self.grok, self.hgs
    gc.collect()

  def testInputLists(self):
    ''' test writing of input list files with climate forcings '''
    grok = self.grok  
    # write lists for fictional scenario
    grok.generateInputLists(lvalidate=self.lvalidate,)
    # convert config file list into string and verify
    output = ''.join(grok._lines) # don't need newlines 
    assert 'precip.inc' in output
    assert 'pet.inc' in output    

  def testParallelIndex(self):
    ''' test writing of parallelindex file '''
    hgs = self.hgs
    pidx_file = self.rundir+hgs.pidx_file
    # write parallelindex file to rundir
    hgs.writeParallelIndex(NP=1, parallelindex=pidx_file) 
    assert os.path.isfile(pidx_file), pidx_file
  
  def testRunGrok(self):
    ''' test the Grok runner command and check if flag is set correctly '''
    hgs = self.hgs  
    exe = '{}/{}'.format(self.hgs_template,self.grok_bin) # run folder not set up
    logfile = '{}/log.grok'.format(hgs.rundir)
    assert hgs.GrokOK is None, hgs.GrokOK
    # climate data
    if not os.path.isdir(self.test_data): raise IOError(self.test_data)
    # run Grok
    if not os.path.isfile(exe): raise IOError(exe)
    ec = hgs.runGrok(executable=exe, logfile=logfile, lerror=False, linput=lbin, ldryrun=not lbin)
    # check output
    batchpfx = self.rundir+hgs.batchpfx
    assert os.path.isfile(batchpfx), batchpfx
    assert os.path.isfile(logfile), logfile
    assert ec == 0, ec
    # check flag
    assert hgs.GrokOK is True, hgs.GrokOK

  def testRunHGS(self):
    ''' test the HGS runner command (will fail without proper folder setup) '''
    hgs = self.hgs  
    exe = '{}/{}'.format(self.hgs_template,self.hgs_bin) # run folder not set up
    logfile = '{}/log.hgs_run'.format(hgs.rundir)
    assert hgs.GrokOK is None, hgs.GrokOK
    # set environment variable for license file
    print('\nHGSDIR: {}'.format(self.hgsdir))
    # attempt to run HGS
    if not os.path.isfile(exe): raise IOError(exe)
    open('{}/SCHEDULED'.format(self.rundir),'a').close() # create fake indicator
    ec = hgs.runHGS(executable=exe, logfile=logfile, skip_grok=True, ldryrun=not lbin)
    # check output
    pidx_file = self.rundir+hgs.pidx_file
    assert os.path.isfile(pidx_file), pidx_file
    assert os.path.isfile(logfile), logfile
    assert ec == 0, ec
    if hgs.HGSOK: indicator = '{}/COMPLETED'.format(self.rundir)
    else: indicator = '{}/FAILED'.format(self.rundir)
    assert os.path.isfile(indicator), indicator
    # check flag
    assert hgs.GrokOK is None, hgs.GrokOK

  def testSetup(self):
    ''' test copying of a run folder from a template '''
    hgs = self.hgs
    if not os.path.isdir(self.hgs_template): raise IOError(self.hgs_template)
    # run setup
    try: 
      hgs.setupRundir(template_folder=self.hgs_template, loverwrite=loverwrite, bin_folder=None)
      # check that all items are there
      assert os.path.isdir(self.rundir), self.rundir
      for exe in (self.hgs_bin, self.grok_bin):
        local_exe = '{}/{}'.format(self.rundir,exe)
        assert os.path.exists(local_exe), local_exe
        indicator = '{}/SCHEDULED'.format(self.rundir)
        assert os.path.exists(indicator), indicator
      print('\nRundir: {}'.format(self.rundir))
    except WindowsError: pass
   
    
## tests for EnsHGS class
class EnsHGSTest(unittest.TestCase):  
  # some HGS test data
  hgs_template = data_root+'/HGS/Templates/GRW-test/' 
  hgs_testcase = 'grw_omafra' # name of test project (for file names)
  test_data    = data_root+'/HGS/Templates/input/clim/climate_forcing/'
  test_prefix  = 'grw2'
  rundir       = '{}/enshgs_test/'.format(workdir,) # test folder
  grok_bin     = 'grok_premium.x' # Grok executable
  hgs_bin      = 'hgs_premium.x' # HGS executable
  hgsdir       = os.getenv('HGSDIR',) # HGS license file  
   
  def setUp(self):
    ''' initialize an HGS ensemble '''
    if not os.path.isdir(self.hgs_template): 
      raise IOError("HGS Template for testing not found:\n '{}'".format(self.hgs_template))
    if os.path.isdir(self.rundir):
      subprocess.call(['rm','-r',self.rundir],) # ignore errors... somehow this is unreliable on Windows...
    os.mkdir(self.rundir) # create new test folder
    # grok test files
    self.grok_input  = '{}/{}.grok'.format(self.hgs_template,self.hgs_testcase)
    self.grok_output = '{}/{}.grok'.format(self.rundir,self.hgs_testcase)
    # some grok settings
    self.runtime = 5*365*24*60*60 # two years in seconds
    self.input_interval = 'monthly'
#     self.input_mode = 'periodic'
    self.input_mode = 'quasi-transient'
    input_folder = data_root+'/HGS/Templates/input/timeseries/climate_forcing/'
    pet_folder = data_root+'/HGS/Templates/input/clim/climate_forcing/'
    # HGS settings
    self.NP = NP
    # create 2-member ensemble
    self.enshgs = EnsHGS(rundir=self.rundir + "/{A}/", project=self.hgs_testcase, runtime=self.runtime,
                         output_interval=(2,12), input_mode=self.input_mode, input_interval=self.input_interval, 
                         input_prefix=self.test_prefix, input_folder=input_folder, pet_folder=pet_folder,
                         NP=self.NP, A=['A1','A2'], outer_list=['A'], template_folder=self.hgs_template,
                         loverwrite=True)
    # load a config file from template
    if not os.path.isfile(self.grok_input):
      raise IOError("Grok configuration file for testing not found:\n '{}'".format(self.grok_input))

  def tearDown(self):
    ''' clean up '''
    del self.enshgs
    gc.collect()
    
  def testInitEns(self):
    ''' initialize the an HGS ensemble using list expansion '''
    # define simple rundir pattern
    rundir = self.rundir + "/{A}/{B}/{C}/"
    rundir_args = dict(A=['A1','A2'], B=['B'], C=['C1','C2'], outer_list=['A','B',('C','input_mode')])
    # initialize ensemble with general and rundir arguments
    enshgs = EnsHGS(rundir=rundir, project=self.hgs_testcase, runtime=self.runtime,
                    input_mode=['steady-state','periodic'], input_interval=self.input_interval, 
                    NP=self.NP, **rundir_args)
    assert len(enshgs) == 4, len(enshgs)
    # test expansion of folder arguments
    for As in rundir_args['A']:
      for Bs in rundir_args['B']:
        for Cs in rundir_args['C']:        
          tmpdir = rundir.format(A=As, B=Bs, C=Cs)
          assert tmpdir in enshgs.rundirs, tmpdir
          # test concurrent expansion of input_mode with folder argument C
          i = enshgs.rundirs.index(tmpdir)
          if Cs == 'C1': assert enshgs.members[i].input_mode == 'steady-state'
          if Cs == 'C2': assert enshgs.members[i].input_mode == 'periodic'
    
  def testSetTime(self):
    ''' mainly just test the method application mechanism '''
    enshgs = self.enshgs
    assert all(rt == self.runtime for rt in enshgs.runtime), enshgs.runtime
    # load Grok file
    enshgs.readConfig(folder=self.hgs_template)
    time = 1 # new runtime
    # setter method
    enshgs.setRuntime(runtime=time)
    assert all(hgs.runtime == time for hgs in enshgs), enshgs.members # EnsHGS supports iteration over members
    assert all(rt == time for rt in enshgs.runtime), enshgs.runtime # EnsHGS supports iteration over members
    #print(enshgs.runtime)
    # using new ensemble wrapper
    time = 10
    enshgs.runtime = time
    assert all(hgs.runtime == time for hgs in enshgs), enshgs.members # EnsHGS supports iteration over members
    assert all(rt == time for rt in enshgs.runtime), enshgs.runtime # EnsHGS supports iteration over members
    
  def testRunEns(self):
    ''' test running the ensemble; the is the primary application test '''
    enshgs = self.enshgs
    assert all(not g for g in enshgs.HGSOK), enshgs.HGSOK
    # check license
    print('\nHGSDIR: {}'.format(self.hgsdir))
    # setup run folders and run Grok
    enshgs.runSimulations(lsetup=True, lgrok=False, loverwrite=loverwrite, skip_grok=True, lparallel=True, NP=2, 
                          runtime_override=120, ldryrun=not lbin) # set runtime to 2 minutes
    assert not lbin or all(g for g in enshgs.HGSOK), enshgs.HGSOK
    for rundir in enshgs.rundirs:
      assert os.path.isdir(rundir), rundir
      if lbin:
        hgslog = '{0}/log.hgs_run'.format(rundir)
        assert os.path.isfile(hgslog), hgslog

  def testSetupExp(self):
    ''' test experiment setup '''
    enshgs = self.enshgs
    assert all(not g for g in enshgs.GrokOK), enshgs.GrokOK
    # setup run folders and run Grok
    enshgs.setupExperiments(lgrok=lbin, loverwrite=loverwrite, lparallel=True)
    assert not lbin or all(g for g in enshgs.GrokOK), enshgs.GrokOK
    for rundir in enshgs.rundirs:
      assert os.path.isdir(rundir), rundir
      if lbin:
        grokfile = '{0}/{1}.grok'.format(rundir,self.hgs_testcase)
        assert os.path.isfile(grokfile), grokfile

  def testSetupRundir(self):
    ''' test rundir setup '''
    enshgs = self.enshgs
    assert all(not g for g in enshgs.GrokOK), enshgs.GrokOK
    # setup run folders
    enshgs.setupExperiments(lgrok=False, loverwrite=loverwrite, lparallel=True)
    for rundir in enshgs.rundirs:
      assert os.path.isdir(rundir), rundir
      grok_bin = '{0}/{1}'.format(rundir,self.grok_bin)
      assert os.path.exists(grok_bin), grok_bin


if __name__ == "__main__":

    
    specific_tests = []
#     specific_tests += ['Class']
#     specific_tests += ['InitEns']
#     specific_tests += ['InputLists']
#     specific_tests += ['ParallelIndex']
#     specific_tests += ['Restart']
#     specific_tests += ['RunEns']
#     specific_tests += ['RunGrok']
#     specific_tests += ['RunHGS']
#     specific_tests += ['SetTime']
#     specific_tests += ['Setup']
#     specific_tests += ['SetupExp']
#     specific_tests += ['SetupRundir']
#     specific_tests += ['Write']


    # list of tests to be performed
    tests = [] 
    # list of variable tests
    tests += ['Grok']
    tests += ['HGS']    
    tests += ['EnsHGS']

    # construct dictionary of test classes defined above
    test_classes = dict()
    local_values = locals().copy()
    for key,val in local_values.items():
      if key[-4:] == 'Test':
        test_classes[key[:-4]] = val


    # run tests
    report = []
    for test in tests: # test+'.test'+specific_test
      if len(specific_tests) > 0: 
        test_names = ['hgsrun_test.'+test+'Test.test'+s_t for s_t in specific_tests]
        s = unittest.TestLoader().loadTestsFromNames(test_names)
      else: s = unittest.TestLoader().loadTestsFromTestCase(test_classes[test])
      report.append(unittest.TextTestRunner(verbosity=2).run(s))
      
    # print summary
    runs = 0; errs = 0; fails = 0
    for name,test in zip(tests,report):
      #print test, dir(test)
      runs += test.testsRun
      e = len(test.errors)
      errs += e
      f = len(test.failures)
      fails += f
      if e+ f != 0: print("\nErrors in '{:s}' Tests: {:s}".format(name,str(test)))
    if errs + fails == 0:
      print("\n   ***   All {:d} Test(s) successfull!!!   ***   \n".format(runs))
    else:
      print("\n   ###     Test Summary:      ###   \n" + 
            "   ###     Ran {:2d} Test(s)     ###   \n".format(runs) + 
            "   ###      {:2d} Failure(s)     ###   \n".format(fails)+ 
            "   ###      {:2d} Error(s)       ###   \n".format(errs))
    