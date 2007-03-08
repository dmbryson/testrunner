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
    self.name = name
    self.tdir = tdir
    
    self.cfg = ConfigParser.ConfigParser()
    self.cfg.read([os.path.join(tdir, "test_list")])
    
    expectdir = os.path.join(tdir, "expected")
    if os.path.exists(expectdir) and os.path.isdir(expectdir): self.has_expected = True
    else: self.has_expected = False
    
    self.app = self.getSetting("main", "app")
    self.args = self.getConfig("main", "args", "")
    
    self.success = True
    self.output = ""
    self.exitcode = 0
    self.errors = []
  # } // End of cTest::cTest()
    
    
  # string cTest::getConfig(string sect, string opt, string default)
  def getConfig(self, sect, opt, default):
    try:
      return self.cfg.get(sect, opt)
    except:
      return default
  # } // End of cTest::getConfig()
  

  # string cTest::getSetting(string sect, string opt) {
  def getSetting(self, sect, opt):
    global settings
    try:
      return self.cfg.get(sect, opt)
    except:
      return settings[opt]
  # } // End of cTest::getSetting()
  
  
  # void cTest::runTest() {
  def runTest(self):
    global tmpdir
    
    confdir = os.path.join(self.tdir, "config")
    rundir = os.path.join(tmpdir, self.name)
    expectdir = os.path.join(self.tdir, "expected")
    
    # Create test directory and populate with config
    shutil.copytree(confdir, rundir)
    

    # Run test app, capturing output and exitcode
    p = popen2.Popen4("cd %s; %s %s" % (rundir, self.app, self.args))
    
    for line in p.fromchild:
      self.output += line + "\n"
    
    self.exitcode = p.wait()
    

    # Non-zero exit code indicates failure, set so and return
    if self.exitcode != 0:
      self.success = False
      shutil.rmtree(rundir, True) # Clean up test directory
      return
      

    # Build dictionary of config structure
    confstruct = {}
    for root, dirs, files in os.walk(confdir):
      if ".svn" in dirs: dirs.remove(".svn")
      for file in files:
        path = os.path.abspath(os.path.join(root, file))
        key = path[len(confdir) + 1:] # remove confdir from path
        confstruct[key] = path
        
      
    # If no expected results exist, copy the results of the command as the new expected results
    if not self.has_expected:
      shutil.copytree(rundir, expectdir)
      for cfile in confstruct.keys():
        try:
          os.remove(os.path.join(expectdir, cfile))
        except OSError, e:
          print "Warning: failed to remove conf file (%s) from expected" % cfile
          print "  -- root cause: %s" % e
      shutil.rmtree(rundir, True) # Clean up test directory
      return

    # Build dicitonary of expected structure
    expectstruct = {}
    for root, dirs, files in os.walk(expectdir):
      if ".svn" in dirs: dirs.remove(".svn")
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
      

  # bool cTest::wasSuccessful() {
  def wasSuccessful(self): return self.success
  # } // End of cTest::wasSuccessful()
    

  # void cTest::reportResults() {
  def reportResults(self):
    print "%s :" % self.name, 
    if self.success:
      if self.has_expected: print "passed"
      else: print "new expected results generated"
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
  usagestr = string.Template("""
Usage: testrunner.py [options]

  Options:
    -h | --help
      Display this message
    
    --builddir=[$builddir]
      Set the path to the build directory
    
    --testdir=[$testdir]
      Set the path to the directory containing tests
""")
  print usagestr.substitute(settings)
# } // End of usage()



# int main(string[] argv) {
def main(argv):
  global cfg, settings, tmpdir

  scriptdir = os.path.abspath(os.path.dirname(argv[0]))
  
  # Read Configuration File
  cfg = ConfigParser.ConfigParser(settings)
  cfg.read([os.path.join(scriptdir, "testrunner.cfg")])
  
  settings["builddir"] = getConfigString("testrunner", "builddir", "build")
  settings["testdir"] = getConfigString("testrunner", "testdir", "tests")

  # Process Command Line Arguments
  try:
    opts, args = getopt.getopt(argv[1:], "h", ["help", "builddir", "testdir"])
  except getopt.GetoptError:
    usage()
    return -1
    
  showhelp = False
  for opt, arg in opts:
    if opt in ("-h", "--help"):
      showhelp = True
    elif opt == "--builddir":
      settings["builddir"] = arg
    elif opt == "--testdir":
      settings["testdir"] = arg
      
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
  sys.stdout.write("Performing tests...")
  sys.stdout.flush()
  for test in tests:
    ti += 1
    sys.stdout.write("\rPerforming tests...  % 4d of %d" % (ti, len(tests)))
    sys.stdout.flush()
    test.runTest()

  sys.stdout.write("\n\n")
  sys.stdout.flush()
  
  # Clean up test directory
  shutil.rmtree(tmpdir, True)

  # Report Results
  success = 0
  fail = 0
  for test in tests:
    test.reportResults()
    if test.wasSuccessful(): success += 1
    else: fail += 1
    
  if fail == 0:
    print "\nAll tests passed."
  else:
    print "\n%d of %d tests failed." % (fail, fail + success)
# } // End of main()  



# void _main() { // Main entry point when called as standalone script
if __name__ == "__main__":
  sys.exit(main(sys.argv))
# } // End of _main()
