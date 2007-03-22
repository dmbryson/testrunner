#!/usr/bin/python

import ConfigParser
import difflib
import dircache
import getopt
import os
import popen2
import shutil
import string
import sys
import tempfile
import threading
import time
import xml.dom.minidom


# Global Constants
TRUE_STRINGS = ("y","Y","yes","Yes","true","True","1")
RESAVAIL = True
EXPECTDIR = "expected"
PERFDIR = "perf~" # subversion, by default, ignores files/dirs with ~ at the end


try:
  import resource
except ImportError:
  RESAVAIL = False


# Global Variables
cfg = None      # ConfigParser.ConfigParser
settings = {}   # {string:string}
tmpdir = None   # string


# // Calculate the median of a sequence
# int med(int[] seq) {
def med(seq):
  seq.sort()
  idx = len(seq) / 2
  if len(seq) % 2 == 1: return seq[idx]
  else: return (seq[idx] + seq[idx - 1]) / 2
# } // End of med()
    

# class cTest {
class cTest:
  NOTFOUND = "file not found"
  DONOTMATCH = "content does not match"
    

  # cTest::cTest(string name, string tdir) {
  def __init__(self, name, tdir):
    global settings, TRUE_STRINGS, RESAVAIL, EXPECTDIR, PERFDIR
    self.name = name
    self.tdir = tdir
    
    if os.path.exists(os.path.join(tdir, settings["svnmetadir"])) and not settings.has_key("disable-svn"): self.usesvn = True
    else: self.usesvn = False

    if settings.has_key("skip-tests"): self.skip = True
    else: self.skip = False
    
    self.cfg = ConfigParser.ConfigParser(settings)
    self.cfg.read([os.path.join(tdir, "test_list")])
    
    expectdir = os.path.join(tdir, EXPECTDIR)
    if os.path.exists(expectdir) and os.path.isdir(expectdir): self.has_expected = True
    else: self.has_expected = False
    
    perfdir = os.path.join(tdir, PERFDIR)
    if os.path.exists(perfdir) and os.path.isdir(perfdir) and os.path.isfile(os.path.join(perfdir, "baseline")):
      self.has_perf_base = True
    else: self.has_perf_base = False
    
    if self.has_perf_base and settings.has_key("reset-perf-base"):
      try:
        rev = "exported"
        if self.usesvn:
          sverp = os.popen("cd %s; %s" % (self.tdir, settings["svnversion"]))
          rev = sverp.readline().strip()
          sverp.close()
          if rev == "": rev = "exported"
        
        oname = "perf-%s-reset-%s" % (time.strftime("%Y-%m-%d-%H.%M.%S"), rev)
        
        shutil.move(os.path.join(perfdir, "baseline"), os.path.join(perfdir, oname))
        print "%s : performance baseline reset" % name
      except (IOError, OSError, shutil.Error): pass

    
    self.app = self.getSetting("main", "app")
    self.args = self.getConfig("main", "args", "")
    
    if self.getConfig("consistency", "enabled", "yes") in TRUE_STRINGS: self.consistency_enabled = True
    else: self.consistency_enabled = False
    if self.getConfig("performance", "enabled", "no") in TRUE_STRINGS and RESAVAIL: self.performance_enabled = True
    else: self.performance_enabled = False
    
    self.success = True
    self.exitcode = 0
    self.errors = []
    
    self.psuccess = True
    self.presult = "passed"
  # } // End of cTest::cTest()
    
    

  # string cTest::getConfig(string sect, string opt, string default)
  def getConfig(self, sect, opt, default):
    global settings
    try:
      return self.cfg.get(sect, opt, False, settings)
    except:
      return default
  # } // End of cTest::getConfig()
  


  # string cTest::getSetting(string sect, string opt) {
  def getSetting(self, sect, opt):
    global settings
    try:
      return self.cfg.get(sect, opt, False, settings)
    except:
      return settings[opt]
  # } // End of cTest::getSetting()
  
  
  
  # bool cTest::isConsistencyTest() {
  def isConsistencyTest(self): return self.consistency_enabled
  # } // End of isConsistencyTest()

  # bool cTest::isPerformanceTest() {
  def isPerformanceTest(self): return self.performance_enabled
  # } // End of isPerformanceTest()
  
  

  # void cTest::runConsistencyTest() {
  def runConsistencyTest(self):
    global settings, tmpdir, EXPECTDIR
    
    if not self.isConsistencyTest(): return
    
    # If no expected results exist and in slave mode, or in master mode and
    # subversion usage has been disabled then skip execution
    if not self.has_expected and (settings["mode"] == "slave" or \
      (settings["mode"] == "master" and not self.usesvn)): return
      
    if self.has_expected and self.skip: return
    
    confdir = os.path.join(self.tdir, "config")
    rundir = os.path.join(tmpdir, self.name)
    expectdir = os.path.join(self.tdir, EXPECTDIR)
    svnmetadir = settings["svnmetadir"]
    
    # Create test directory and populate with config
    try:
      shutil.copytree(confdir, rundir)
    except (IOError, OSError):
      self.success = False
      return
      
    
    # Remove copied svn metadata directories
    for root, dirs, files in os.walk(rundir):
      if svnmetadir in dirs: dirs.remove(svnmetadir)
      try:
        shutil.rmtree(os.path.join(root, svnmetadir))
      except (IOError, OSError): pass
          

    # Run test app, capturing output and exitcode
    p = popen2.Popen4("cd %s; %s %s" % (rundir, self.app, self.args))
    
    # Process output from app
    # Note: must at least swallow app output so that the process output buffer does not fill and block execution
    if settings.has_key("verbose"): print
    for line in p.fromchild:
      if settings.has_key("verbose"):
        sys.stdout.write("%s output: %s" % (self.name, line))
        sys.stdout.flush()
    
    self.exitcode = p.wait()
    

    # Non-zero exit code indicates failure, set so and return
    if self.exitcode != 0:
      self.success = False
      try:
        shutil.rmtree(rundir, True) # Clean up test directory
      except (IOError, OSError): pass
      return
      

    # Build dictionary of config structure
    confstruct = {}
    for root, dirs, files in os.walk(confdir):
      if svnmetadir in dirs: dirs.remove(svnmetadir)
      for file in files:
        path = os.path.abspath(os.path.join(root, file))
        key = path[len(confdir) + 1:] # remove confdir from path
        confstruct[key] = path
        
      
    # If no expected results exist, defer processing of new expected results to results phase
    if not self.has_expected: 
      self.confstruct = confstruct
      return

    # Build dicitonary of expected structure
    expectstruct = {}
    for root, dirs, files in os.walk(expectdir):
      if svnmetadir in dirs: dirs.remove(svnmetadir)
      for file in files:
        path = os.path.abspath(os.path.join(root, file))
        key = path[len(expectdir) + 1:] # remove confdir from path
        expectstruct[key] = [path, False, cTest.NOTFOUND]

    # Traverse results, comparing with expected
    for root, dirs, files in os.walk(rundir):
      for file in files:
        path = os.path.abspath(os.path.join(root, file))
        key = path[len(rundir) + 1:] # remove confdir from path
        if expectstruct.has_key(key):
          # string[] getStippedLines(string filename) {
          def getStrippedLines(filename):
            fp = open(filename, "U")
            filelines = fp.readlines()
            fp.close()
            
            retlines = []
            for line in filelines: 
              line = string.lstrip(line)
              if len(line) != 0 and line[0] != "#": retlines.append(line)
            return retlines
          # } // End of getStrippedLines()
          
          # Generate the diff between the two files, ignoring comments and blank lines
          differ = difflib.Differ()
          elines = getStrippedLines(path)
          tlines = getStrippedLines(expectstruct[key][0])
          diff = list(differ.compare(elines, tlines))

          match = True
          for line in diff:
            if line[0] != ' ':
              expectstruct[key][2] = cTest.DONOTMATCH
              match = False
              break
          
          expectstruct[key][1] = match
    
    for key in expectstruct.keys():
      entry = expectstruct[key]
      if not entry[1]:
        self.errors.append("%s : %s" % (key, entry[2]))
        self.success = False

    # Clean up test directory
    try:
      shutil.rmtree(rundir, True)
    except (IOError, OSError): pass
  # } // End of cTest::runConsistencyTest()



  # void cTest::runPerformanceTest() {
  def runPerformanceTest(self):
    global settings, tmpdir, PERFDIR
    
    if not self.isPerformanceTest(): return
    
    if self.has_perf_base and self.skip:
      self.presult = "skipped"
      return
    
    confdir = os.path.join(self.tdir, "config")
    rundir = os.path.join(tmpdir, self.name)
    perfdir = os.path.join(self.tdir, PERFDIR)
    svnmetadir = settings["svnmetadir"]
    
    # Create test directory and populate with config
    try:
      shutil.copytree(confdir, rundir)
    except (IOError, OSError):
      self.psuccess = False
      self.presult = "error occured creating run directory"
      return
      
    
    # Remove copied svn metadata directories
    for root, dirs, files in os.walk(rundir):
      if svnmetadir in dirs: dirs.remove(svnmetadir)
      try:
        shutil.rmtree(os.path.join(root, svnmetadir))
      except (IOError, OSError): pass
    
    
    # Run warm up
    p = popen2.Popen4("cd %s; %s %s" % (rundir, self.app, self.args))
    
    # Process output from app
    # Note: must at least swallow app output so that the process output buffer does not fill and block execution
    if settings.has_key("verbose"): print
    for line in p.fromchild:
      if settings.has_key("verbose"):
        sys.stdout.write("%s output: %s" % (self.name, line))
        sys.stdout.flush()
    
    exitcode = p.wait()

    # Non-zero exit code indicates failure, set so and return
    if exitcode != 0:
      try:
        shutil.rmtree(rundir, True) # Clean up test directory
      except (IOError, OSError): pass
      self.psuccess = False
      self.presult = "test app returned non-zero exit code"
      return
    
    
    # Run test X times, take min value
    times = []
    for i in range(settings["perf_repeat"]):
      res_start = resource.getrusage(resource.RUSAGE_CHILDREN)
      
      # Run test app, capturing output and exitcode
      p = popen2.Popen4("cd %s; %s %s" % (rundir, self.app, self.args))
      
    # Process output from app
    # Note: must at least swallow app output so that the process output buffer does not fill and block execution
    if settings.has_key("verbose"): print
    for line in p.fromchild:
      if settings.has_key("verbose"):
        sys.stdout.write("%s output: %s" % (self.name, line))
        sys.stdout.flush()
      
      exitcode = p.wait()
      res_end = resource.getrusage(resource.RUSAGE_CHILDREN)
  
      # Non-zero exit code indicates failure, set so and return
      if exitcode != 0:
        try:
          shutil.rmtree(rundir, True) # Clean up test directory
        except (IOError, OSError): pass
        self.psuccess = False
        self.presult = "test app returned non-zero exit code"
        return
      
      times.append(res_end.ru_utime - res_start.ru_utime)
      
    
    # Load baseline results
    baseline = 0.0
    basepath = os.path.join(perfdir, "baseline")
    if self.has_perf_base:
      try:
        fp = open(basepath, "r")
        line = fp.readline()
        baseline = float(line.split(',')[0].strip())
        fp.close()
      except (IOError):
        self.has_perf_base = False
    

    tmin = min(times)
    tmax = max(times)
    tave = sum(times) / len(times)
    tmed = med(times)
    
    # If no baseline results exist, write out results
    if not self.has_perf_base:
      try:
        if not os.path.exists(perfdir):
          os.mkdir(perfdir)
        if not os.path.isdir(perfdir):
          try:
            shutil.rmtree(rundir, True) # Clean up test directory
          except (IOError, OSError): pass
          self.psuccess = False
          self.presult = "unable to write out baseline, file exists"
          return
          
        fp = open(basepath, "w")
        fp.write("%f,%f,%f,%f\n" % (tmin, tmax, tave, tmed))
        fp.flush()
        fp.close()
      except (IOError):
        try:
          shutil.rmtree(rundir, True) # Clean up test directory
        except (IOError, OSError): pass
        self.psuccess = False
        self.presult = "error occurred writing baseline results"
        return

      try:
        shutil.rmtree(rundir, True) # Clean up test directory
      except (IOError, OSError): pass
      self.presult = "new baseline - min: %3.4f max: %3.4f ave: %3.4f med: %3.4f" % (tmin, tmax, tave, tmed)
      return
      
    # Compare results with baseline
    margin = settings["perf_margin"] * baseline
    umargin = baseline + margin
    lmargin = baseline - margin
    
    if tmin > umargin:
      self.psuccess = False
      self.presult = "failed - base: %3.4f test: %3.4f" % (baseline, tmin)
    elif tmin < lmargin:
      # new baseline, move old baseline and write out new results
      try:
        rev = "exported"
        if self.usesvn:
          sverp = os.popen("cd %s; %s" % (self.tdir, settings["svnversion"]))
          rev = sverp.readline().strip()
          sverp.close()
          if rev == "": rev = "exported"
        
        oname = "perf-%s-prev-%s" % (time.strftime("%Y-%m-%d-%H.%M.%S"), rev)
        
        shutil.move(basepath, os.path.join(perfdir, oname))
        
        fp = open(basepath, "w")
        fp.write("%f,%f,%f,%f\n" % (tmin, tmax, tave, tmed))
        fp.flush()
        fp.close()
      except (IOError, OSError, shutil.Error):
        try:
          shutil.rmtree(rundir, True) # Clean up test directory
        except (IOError, OSError): pass
        self.presult = "exceeded - base: %3.4f test: %3.4f - failed to update" % (baseline, tmin)
        return

      self.presult = "exceeded - base: %3.4f test: %3.4f - updated baseline" % (baseline, tmin)
    
    # Clean up test directory
    try:
      shutil.rmtree(rundir, True)
    except (IOError, OSError): pass
  # } // End of cTest::runPerformanceTest()
  
  
  
  # string cTest::getRepositoryPath(string ) {
  def getRepositoryPath(self):
    global settings
    
    ifp = os.popen("%s info --xml %s" % (settings["svn"], settings["testdir"]))
    doc = xml.dom.minidom.parse(ifp)
    if doc.documentElement.tagName != "info": return ""
    
    urltags = doc.getElementsByTagName("url")
    if len(urltags) < 1 or urltags[0].firstChild.nodeType != urltags[0].firstChild.TEXT_NODE: return ""
    return urltags[0].firstChild.data
  # } // End of cTest::getRepositoryPath()
  


  # bool cTest::handleNewExpected() {
  def handleNewExpected(self):
    global settings, EXPECTDIR
    
    if settings["mode"] == "slave": return True

    rundir = os.path.join(tmpdir, self.name)
    expectdir = os.path.join(self.tdir, EXPECTDIR)
    
    svn = settings["svn"]

    if settings["mode"] == "master":
      if not self.usesvn: return True
      svndir = os.path.join(tmpdir, "_svn_tests")
      if not os.path.exists(svndir):
        ecode = os.spawnlp(os.P_WAIT, svn, svn, "checkout", "-q", self.getRepositoryPath(), svndir)
        if ecode != 0: return False
      expectdir = os.path.join(svndir, self.name, EXPECTDIR)

    try:
      shutil.copytree(rundir, expectdir)
    except (IOError, OSError):
      return False

    for cfile in self.confstruct.keys():
      try:
        os.remove(os.path.join(expectdir, cfile))
      except OSError, e:
        print "Warning: failed to remove conf file (%s) from expected" % cfile
        print "  -- root cause: %s" % e
    try:
      shutil.rmtree(rundir, True) # Clean up test directory
    except (IOError, OSError): pass
    if self.usesvn:
      ecode = os.spawnlp(os.P_WAIT, svn, svn, "add", expectdir)
      if ecode != 0: return False

    return True
    
  # } // End of cTest::handleNewExpected()



  # bool cTest::reportConsistencyResults() {
  def reportConsistencyResults(self):
    global settings
    print "%s :" % self.name, 
    if self.success:
      if self.has_expected:
        if self.skip:
          print "skipped"
        else:
          print "passed"
      else:
        if self.handleNewExpected():
          if settings["mode"] == "slave": print "no expected results, skipped"
          else: print "new expected results generated"
        else:
          print "unable to process new expected results"
          self.success = False
    else:
      print "failed\n"
      if self.exitcode != 0:
        print "exit code: %d" % self.exitcode
      else:
        print "output variance(s):"
        for err in self.errors: print err
      print "\n"

    return self.success
  # } // End of cTest::reportConsistencyResults()
  
  
  
  # bool cTest::reportPerformanceResults() {
  def reportPerformanceResults(self):
    print "%s : %s" % (self.name, self.presult) 
    return self.psuccess
  # } // End of cTest::reportPerformanceResults()
  
  
  
  # void cTest::describe() {
  def describe(self):
    if self.has_expected: print "  ",
    else: print "* ",
    print self.name
  # } // End of cTest::describe()
    
# } // End of class cTest




# string getConfig(string sect, string opt, string default) {
def getConfig(sect, opt, default):
  try:
    global cfg, settings
    val = cfg.get(sect, opt, False, settings)
    return val
  except:
    return default
# } // End of getConfig()



# void usage() {
def usage():
  global settings
  usagestr = """
Usage: %(_testrunner_name)s [options] [testname ...]

  Runs the specified tests.  If no tests are specified all available tests will
  be run and new expected results generated, where applicable.

  Options:
    -h | --help
      Display this message
    
    --builddir=dir [%(builddir)s]
      Set the path to the build directory.
    
    --disable-svn
      Disable all Subversion usage.
    
    -j number [%(cpus)d]
      Set the number of concurrent tests to run. i.e. - the number of CPUs
      that are availabile.
      
    -l | --list-tests
      List all available tests and exits.  Tests that will require new
      expected results will have an asterisk preceeding the name.
      
    --mode=option [%(mode)s]
      Set the test runner mode.  Options are 'local', 'master', and 'slave'.
      
      Local mode generates expected results and adds them to the repository,
      if subversion metadata has been found.  Master mode does the same as
      local, but also commits the generated expected results automatically.
      Slave mode disables expected results generation completely.
      
    -p | --run-perf-tests
      Run available performance tests.
      
    --reset-perf-base
      Reset performance test baseline results.  Old baseline results are
      saved in the 'perf' directory.

    --skip-tests
      Do not run tests. Only generate new results, where applicable.

    -s path | --svn=path [%(svn)s]
      Set the path to the Subversion command line utility.

    --svnversion=path [%(svnversion)s]
      Set the path to the Subversion 'svnversion' command line utility.
    
    --svnmetadir=dir [%(svnmetadir)s]
      Set the name of the Subversion metadata directory.
    
    --testdir=dir [%(testdir)s]
      Set the path to the directory containing tests.
    
    -v | --verbose
      Enable verbose output, showing all test output.
""" % settings
  print usagestr
# } // End of usage()



# (int, int) runConsistencyTests(cTest[] tests) {
def runConsistencyTests(alltests):
  global settings, tmpdir
  
  tests = []
  for test in alltests:
    if test.isConsistencyTest(): tests.append(test)
  
  if len(tests) == 0:
    print "No Consistency Tests Available (or Specified)."
    return (0, 0)

  print "\nRunning Consistency Tests..."
  
  # Run Tests
  sem = threading.BoundedSemaphore(settings["cpus"])
  ti = 0
  sys.stdout.write("Performing Test:")
  sys.stdout.flush()
  for test in tests:
    # void runTestWrapper(cTest test, Semaphore sem) {
    def runTestWrapper(test, sem):
      test.runConsistencyTest()
      sem.release()  
    # } // End of runTestWrapper()

    sem.acquire()
    ti += 1
    sys.stdout.write("\rPerforming Test:  % 4d of %d" % (ti, len(tests)))
    sys.stdout.flush()
    tthread = threading.Thread(target=runTestWrapper, args=(test, sem))
    tthread.start()
  
  for i in range(settings["cpus"]): sem.acquire()

  sys.stdout.write("\n\n")
  sys.stdout.flush()


  # Report Results
  success = 0
  fail = 0
  for test in tests:
    if test.reportConsistencyResults(): success += 1
    else: fail += 1

  svndir = os.path.join(tmpdir, "_svn_tests")
  if os.path.exists(svndir) and not settings.has_key("disable-svn"):
    print "\nAdding new expected results to the repository..."
    svn = settings["svn"]
    ecode = os.spawnlp(os.P_WAIT, svn, svn, "commit", svndir, "-m", "Adding new expected results.")
    if ecode != 0: print "Error: Failed to add new expected results."
  
  return (success, fail)
# } // End of runConsistencyTests()



# (int, int) runPerformanceTests(cTest[] tests) {
def runPerformanceTests(alltests):
  global settings, tmpdir
  
  tests = []
  for test in alltests:
    if test.isPerformanceTest(): tests.append(test)
  
  if len(tests) == 0:
    print "No Performance Tests Available (or Specified)."
    return (0, 0)

  print "\nRunning Performance Tests..."
  
  # Run Tests
  ti = 0
  sys.stdout.write("Performing Test:")
  sys.stdout.flush()
  for test in tests:
    ti += 1
    sys.stdout.write("\rPerforming Test:  % 4d of %d" % (ti, len(tests)))
    sys.stdout.flush()
    test.runPerformanceTest()
  
  sys.stdout.write("\n\n")
  sys.stdout.flush()


  # Report Results
  success = 0
  fail = 0
  for test in tests:
    if test.reportPerformanceResults(): success += 1
    else: fail += 1

  return (success, fail)
# } // End of runPerformanceTests()



# int main(string[] argv) {
def main(argv):
  global cfg, settings, tmpdir

  scriptdir = os.path.abspath(os.path.dirname(argv[0]))
  
  # Read Configuration File
  cfg = ConfigParser.ConfigParser(settings)
  cfg.read([os.path.join(scriptdir, "testrunner.cfg")])
  
  settings["builddir"] = getConfig("testrunner", "builddir", "build")
  settings["mode"] = getConfig("testrunner", "mode", "local")
  settings["svn"] = getConfig("testrunner", "svn", "svn")
  settings["svnversion"] = getConfig("testrunner", "svnversion", "svnversion")
  settings["svnmetadir"] = getConfig("testrunner", "svnmetadir", ".svn")
  settings["testdir"] = getConfig("testrunner", "testdir", "tests")

  settings["_testrunner_name"] = "testrunner.py"
  
  settings["perf_margin"] = float(getConfig("performance","maring",.05))
  settings["perf_repeat"] = int(getConfig("performance","repeat",5))

  settings["cpus"] = 1

  # Process Command Line Arguments
  try:
    opts, args = getopt.getopt(argv[1:], "hj:lm:ps:v", \
      ["builddir=", "disable-svn", "help", "list-tests", "mode=", "reset-perf-base", "run-perf-tests", "skip-tests", \
       "svnmetadir=", "svn=", "svnversion=", "testdir=", "verbose", "-testrunner-name="])
  except getopt.GetoptError:
    usage()
    return -1
    
  opt_showhelp = False
  opt_listtests = False
  opt_runperf = False
  for opt, arg in opts:
    if opt in ("-h", "--help"):
      opt_showhelp = True
    elif opt == "--builddir":
      settings["builddir"] = arg
    elif opt == "-j":
      cpus = int(arg)
      if cpus < 1: cpus = 1
      settings["cpus"] = cpus
    elif opt == "--disable-svn":
      settings["disable-svn"] = ""
    elif opt in ("-l", "--list-tests"):
      opt_listtests = True
    elif opt in ("-m", "--mode"):
      settings["mode"] = arg
    elif opt == "--reset-perf-base":
      settings["reset-perf-base"] = ""
    elif opt in ("-p", "--run-perf-tests"):
      opt_runperf = True
    elif opt == "--skip-tests":
      settings["skip-tests"] = ""
    elif opt == "--svnmetadir":
      settings["svnmetadir"] = arg
    elif opt in ("-s", "--svn"):
      settings["svn"] = arg
    elif opt == "--svnversion":
      settings["svnversion"] = arg
    elif opt == "--testdir":
      settings["testdir"] = arg
    elif opt in ("-v", "--verbose"):
      settings["verbose"] = ""
    elif opt == "---testrunner-name":
      settings["_testrunner_name"] = arg
      
  # Show help and exit, if requested to do so
  if opt_showhelp:
    usage()
    return 0
  
  
  # Load the app to test, check for its existance
  app = getConfig("main", "app", "")
  if app == "":
    print "Warning: No default test app configured"
  else:
    app = os.path.abspath(app)
    if not os.path.exists(app) and not os.path.isfile(app):
      print "Error: invalid test app"
      return -1
  settings['app'] = app
  

  testdir = os.path.abspath(getConfig("main", "testdir", "."))  
  settings["testdir"] = testdir

  
  # Load in all tests
  print "Reading Test Configurations..."
  tests = []
  
  dlist = args
  if len(dlist) == 0: dlist = dircache.listdir(testdir)
  
  dircache.annotate(testdir, dlist)
  for d in dlist:
    # Directories with preceeding underscore or period are ignored, as are files
    if d[0] == "_" or d[0] == "." or d[len(d) - 1] != "/": continue
    
    name = d[:len(d) - 1]
    curtdir = os.path.join(testdir, name)
    contents = dircache.listdir(curtdir)
    if "config" in contents:
      tests.append(cTest(name, curtdir))


  # If selected, display available tests and exit
  if opt_listtests:
    print "Available Tests:\n"
    for test in tests: test.describe()
    return 0

  # Make temp directory to hold active tests  
  tmpdir = tempfile.mkdtemp("_testrunner")


  # Run Consistency Tests
  (success, fail) = runConsistencyTests(tests)
  
  if fail == 0 and opt_runperf:
    (psuccess, pfail) = runPerformanceTests(tests)
    success += psuccess
    fail += pfail

  # Clean up test directory
  try:
    shutil.rmtree(tmpdir, True)
  except (IOError, OSError): pass


  if fail == 0:
    print "\nAll tests passed."
    return 0
  else:
    print "\n%d of %d tests failed." % (fail, fail + success)
    return fail
  
# } // End of main()  




# void _main() { // Main entry point when called as standalone script
if __name__ == "__main__":
  sys.exit(main(sys.argv))
# } // End of _main()
