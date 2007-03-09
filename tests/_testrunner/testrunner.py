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
import time
import xml.dom.minidom

import pprint

# Global Variables
cfg = None      # ConfigParser.ConfigParser
settings = {}   # {string:string}
tmpdir = None   # string


# class cTest {
class cTest:
  NOTFOUND = "file not found"
  DONOTMATCH = "content does not match"
  

  # cTest::cTest(string name, string tdir) {
  def __init__(self, name, tdir):
    global settings
    self.name = name
    self.tdir = tdir
    
    if os.path.exists(os.path.join(tdir, settings["svnmetadir"])) and not settings.has_key("disable-svn"): self.usesvn = True
    else: self.usesvn = False
    
    self.cfg = ConfigParser.ConfigParser(settings)
    self.cfg.read([os.path.join(tdir, "test_list")])
    
    expectdir = os.path.join(tdir, "expected")
    if os.path.exists(expectdir) and os.path.isdir(expectdir): self.has_expected = True
    else: self.has_expected = False
    
    self.app = self.getSetting("main", "app")
    self.args = self.getConfig("main", "args", "")
    
    self.success = True
    self.exitcode = 0
    self.errors = []
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
  
  

  # void cTest::runTest() {
  def runTest(self):
    global settings, tmpdir
    
    # If no expected results exist and in slave mode, or in master mode and
    # subversion usage has been disabled then skip execution
    if not self.has_expected and (settings["mode"] == "slave" or \
      (settings["mode"] == "master" and not self.usesvn)): return
    
    confdir = os.path.join(self.tdir, "config")
    rundir = os.path.join(tmpdir, self.name)
    expectdir = os.path.join(self.tdir, "expected")
    svnmetadir = settings["svnmetadir"]
    
    # Create test directory and populate with config
    shutil.copytree(confdir, rundir)
    
    # Remove copied svn metadata directories
    for root, dirs, files in os.walk(rundir):
      if svnmetadir in dirs: dirs.remove(svnmetadir)
      shutil.rmtree(os.path.join(root, svnmetadir))
          

    # Run test app, capturing output and exitcode
    p = popen2.Popen4("cd %s; %s %s" % (rundir, self.app, self.args))
    
    if settings.has_key("verbose"):
      print
      for line in p.fromchild: print "%s output: %s" % (self.name, line)
    
    self.exitcode = p.wait()
    

    # Non-zero exit code indicates failure, set so and return
    if self.exitcode != 0:
      self.success = False
      shutil.rmtree(rundir, True) # Clean up test directory
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
    shutil.rmtree(rundir, True)
  # } // End of cTest::runTest()
  
  
  
  # string cTest::getRepositoryPath(string ) {
  def getRepositoryPath(self):
    global settings
    
    ifp = os.popen("%s info --xml %s" % (settings["svnpath"], settings["testdir"]))
    doc = xml.dom.minidom.parse(ifp)
    if doc.documentElement.tagName != "info": return ""
    
    urltags = doc.getElementsByTagName("url")
    if len(urltags) < 1 or urltags[0].firstChild.nodeType != urltags[0].firstChild.TEXT_NODE: return ""
    return urltags[0].firstChild.data
  # } // End of cTest::getRepositoryPath()
  


  # bool cTest::handleNewExpected() {
  def handleNewExpected(self):
    global settings

    rundir = os.path.join(tmpdir, self.name)
    expectdir = os.path.join(self.tdir, "expected")
    
    svn = settings["svnpath"]

    if settings["mode"] == "master":
      if not self.usesvn: return True
      svndir = os.path.join(tmpdir, "_svn_tests")
      if not os.path.exists(svndir):
        ecode = os.spawnlp(os.P_WAIT, svn, svn, "checkout", "-q", self.getRepositoryPath(), svndir)
        if ecode != 0: return False
      expectdir = os.path.join(svndir, self.name, "expected")

    shutil.copytree(rundir, expectdir)
    for cfile in self.confstruct.keys():
      try:
        os.remove(os.path.join(expectdir, cfile))
      except OSError, e:
        print "Warning: failed to remove conf file (%s) from expected" % cfile
        print "  -- root cause: %s" % e
    shutil.rmtree(rundir, True) # Clean up test directory
    if self.usesvn:
      ecode = os.spawnlp(os.P_WAIT, svn, svn, "add", expectdir)
      if ecode != 0: return False

    return True
    
  # } // End of cTest::handleNewExpected()



  # bool cTest::wasSuccessful() {
  def wasSuccessful(self): return self.success
  # } // End of cTest::wasSuccessful()
    


  # void cTest::reportResults() {
  def reportResults(self):
    print "%s :" % self.name, 
    if self.success:
      if self.has_expected: print "passed"
      else:
        if self.handleNewExpected():
          print "new expected results generated"
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
  # } // End of cTest::reportResults()
    
# } // End of class cTest




# string getConfigString(string sect, string opt, string default) {
def getConfigString(sect, opt, default):
  try:
    global cfg, settings
    val = cfg.get(sect, opt, False, settings)
    return val
  except:
    return default
# } // End of getConfigString()




# void usage() {
def usage():
  global settings
  usagestr = """
Usage: testrunner.py [options]

  Options:
    -h | --help
      Display this message
    
    --builddir=[%(builddir)s]
      Set the path to the build directory.
    
    --disable-svn
      Disable all Subversion usage.
      
    --mode=[%(mode)s]
      Set the test runner mode.  Options are 'local', 'master', and 'slave'.
      
      Local mode generates expected results and adds them to the repository,
      if subversion metadata has been found.  Master mode does the same as
      local, but also commits the generated expected results automatically.
      Slave mode disables expected results generation completely.

    -s [%(svnpath)s] | --svnpath=[%(svnpath)s]
      Set the path to the Subversion command line utility.
    
    --svnmetadir=[%(svnmetadir)s]
      Set the name of the Subversion metadata directory.
    
    --testdir=[%(testdir)s]
      Set the path to the directory containing tests.
    
    -v | --verbose
      Enable verbose output, showing all test output.
""" % settings
  print usagestr
# } // End of usage()




# int main(string[] argv) {
def main(argv):
  global cfg, settings, tmpdir

  scriptdir = os.path.abspath(os.path.dirname(argv[0]))
  
  # Read Configuration File
  cfg = ConfigParser.ConfigParser(settings)
  cfg.read([os.path.join(scriptdir, "testrunner.cfg")])
  
  settings["builddir"] = getConfigString("testrunner", "builddir", "build")
  settings["mode"] = getConfigString("testrunner", "mode", "local")
  settings["svnpath"] = getConfigString("testrunner", "svnpath", "svn")
  settings["svnmetadir"] = getConfigString("testrunner", "svnmetadir", ".svn")
  settings["testdir"] = getConfigString("testrunner", "testdir", "tests")

  # Process Command Line Arguments
  try:
    opts, args = getopt.getopt(argv[1:], "hm:s:v", \
      ["builddir=", "disable-svn", "help", "mode=", "svnmetadir=", "svnpath=", "testdir=", "verbose"])
  except getopt.GetoptError:
    usage()
    return -1
    
  showhelp = False
  for opt, arg in opts:
    if opt in ("-h", "--help"):
      showhelp = True
    elif opt == "--builddir":
      settings["builddir"] = arg
    elif opt in ("-m", "--mode"):
      settings["mode"] = arg
    elif opt == "--disable-svn":
      settings["disable-svn"] = ""
    elif opt == "--svnmetadir":
      settings["svnmetadir"] = arg
    elif opt in ("-s", "--svnpath"):
      settings["svnpath"] = arg
    elif opt == "--testdir":
      settings["testdir"] = arg
    elif opt in ("-v", "--verbose"):
      settings["verbose"] = ""
      
  # Show help and exit, if requested to do so
  if showhelp:
    usage()
    return 0
  
  
  # Load the app to test, check for its existance
  app = getConfigString("main", "app", "")
  if app == "":
    print "Warning: No default test app configured"
  else:
    app = os.path.abspath(app)
    if not os.path.exists(app) and not os.path.isfile(app):
      print "Error: invalid test app"
      return -1
  settings['app'] = app
  
  # Load in all tests
  print "Reading test configurations..."
  tests = []

  testdir = os.path.abspath(getConfigString("main", "testdir", "."))  
  settings["testdir"] = testdir
  tlist = dircache.listdir(testdir)
  dircache.annotate(testdir, tlist)
  for test in tlist:
    # Directories with preceeding underscore or period are ignored, as are files
    if test[0] == "_" or test[0] == "." or test[len(test) - 1] != "/": continue
    
    name = test[:len(test) - 1]
    curtdir = os.path.join(testdir, name)
    contents = dircache.listdir(curtdir)
    if "config" in contents:
      tests.append(cTest(name, curtdir))


  # Make temp directory to hold active tests  
  tmpdir = tempfile.mkdtemp("_testrunner")


  # Run tests
  ti = 0
  sys.stdout.write("Performing Test:")
  sys.stdout.flush()
  for test in tests:
    ti += 1
    sys.stdout.write("\rPerforming Test:  % 4d of %d" % (ti, len(tests)))
    sys.stdout.flush()
    test.runTest()

  sys.stdout.write("\n\n")
  sys.stdout.flush()
  
  # Report Results
  success = 0
  fail = 0
  for test in tests:
    test.reportResults()
    if test.wasSuccessful(): success += 1
    else: fail += 1

  svndir = os.path.join(tmpdir, "_svn_tests")
  if os.path.exists(svndir) and not settings.has_key("disable-svn"):
    print "\nAdding new expected results to the repository..."
    svn = settings["svnpath"]
    ecode = os.spawnlp(os.P_WAIT, svn, svn, "commit", svndir, "-m", "Adding new expected results.")
    if ecode != 0: print "Error: Failed to add new expected results."

  # Clean up test directory
  shutil.rmtree(tmpdir, True)
    
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
