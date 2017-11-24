import os, platform, re, sys, threading, time, traceback;
sTestsFolderPath = os.path.dirname(os.path.abspath(__file__));
sBugIdFolderPath = os.path.dirname(sTestsFolderPath);
sBaseFolderPath = os.path.dirname(sBugIdFolderPath);
sys.path.extend([
  sBaseFolderPath,
  sBugIdFolderPath,
  os.path.join(sBugIdFolderPath, "modules"),
]);

bDebugStartFinish = False;  # Show some output when a test starts and finishes.
gbDebugIO = False;          # Show cdb I/O during tests (you'll want to run only 1 test at a time for this).

from cBugId import cBugId;
from cBugReport_foAnalyzeException_STATUS_ACCESS_VIOLATION import ddtsDetails_uSpecialAddress_sISA;
from mFileSystem import mFileSystem;
from mWindowsAPI import fsGetOSISA;

dsComSpec_by_sISA = {};
dsComSpec_by_sISA[fsGetOSISA()] = os.path.join(os.environ.get("WinDir"), "System32", "cmd.exe");
if fsGetOSISA() == "x64":
  dsComSpec_by_sISA["x86"] = os.path.join(os.environ.get("WinDir"), "SysWOW64", "cmd.exe");

cBugId.dxConfig["bShowAllCdbCommandsInReport"] = True;
cBugId.dxConfig["nExcessiveCPUUsageCheckInterval"] = 10; # The test application is simple: CPU usage should be apparent after a few seconds.
cBugId.dxConfig["uArchitectureIndependentBugIdBits"] = 32; # Test architecture independent bug ids

sPythonISA = {
  "32bit": "x86",
  "64bit": "x64",
}[platform.architecture()[0]];
asTestISAs = {
  "x86": ["x86"],
  "x64": ["x64", "x86"],
}[sPythonISA];

sReportsFolderName = mFileSystem.fsPath(sBugIdFolderPath, "Tests", "Reports");

dsBinaries_by_sISA = {
  "x86": os.path.join(sTestsFolderPath, r"bin\Tests_x86.exe"),
  "x64": os.path.join(sTestsFolderPath, r"bin\Tests_x64.exe"),
  "fail": os.path.join(sTestsFolderPath, r"bin\Binary_does_not_exist.exe"),
};

bFailed = False;
gbGenerateReportHTML = False;
oOutputLock = threading.Lock();
guTotalMaxMemoryUse =  0x01234567; # Should be large enough to allow the application to allocate some memory, but small
                                   # enough to detect excessive memory allocations before all memory on the system is
                                   # used.
guLargeHeapBlockSize = 0x00800000; # Should be large to detect potential issues when handling large allocations, but
                                   # not so large as to cause the application to allocate more memory than it is allowed
                                   # through the guTotalMaxMemoryUse variable.

guLastLineLength = 0;
def fOutput(sMessage = "", bCRLF = True):
  global guLastLineLength;
  oOutputLock and oOutputLock.acquire();
  sPaddedMessage = sMessage.ljust(guLastLineLength);
  if bCRLF:
    print sPaddedMessage;
    guLastLineLength = 0;
  else:
    print (sPaddedMessage + "\r"),;
    guLastLineLength = len(sMessage);
  oOutputLock and oOutputLock.release();
  
gbTestFailed = False;

def fTest(
  sISA,
  axCommandLineArguments,
  sExpectedBugId,
  sExpectedFailedToDebugApplicationErrorMessage = None,
  bRunInShell = False,
  sApplicationBinaryPath = None,
  sExpectedBugLocationFunctionName = None
):
  global gbTestFailed;
  if gbTestFailed:
    return;
  asApplicationArguments = axCommandLineArguments and [
    isinstance(x, str) and x
             or x < 10 and ("%d" % x)
                        or ("0x%X" % x)
    for x in axCommandLineArguments
  ] or [];
  if sApplicationBinaryPath is None:
    sApplicationBinaryPath = dsBinaries_by_sISA[sISA];
  asCommandLine = [sApplicationBinaryPath] + asApplicationArguments;
  sFailedToDebugApplicationErrorMessage = None;
  if sExpectedFailedToDebugApplicationErrorMessage:
    sExpectedBugLocation = None;
    sTestDescription = "%s => %s" % ("Running %s" % sApplicationBinaryPath, repr(sExpectedFailedToDebugApplicationErrorMessage));
  else:
    sExpectedBugLocation = "%s!%s" % \
        (os.path.basename(sApplicationBinaryPath).lower(), sExpectedBugLocationFunctionName or "wmain");
    sTestDescription = "%s on %s%s => %s @ %s" % (" ".join(asApplicationArguments), sISA, \
        bRunInShell and " (in child process)" or "", sExpectedBugId, sExpectedBugLocation);

  if bRunInShell:
    asApplicationArguments = ["/C", sApplicationBinaryPath] + asApplicationArguments; 
    sApplicationBinaryPath = dsComSpec_by_sISA[sISA];
  
  if bDebugStartFinish:
    fOutput("* Started %s" % sTestDescription);
  else:
    fOutput("* %s" % sTestDescription, bCRLF = False);
  
  asLog = [];
  def fStdInInputHandler(oBugId, sInput):
    if gbDebugIO: fOutput("stdin<%s" % sInput);
    asLog.append("stdin<%s" % sInput);
  def fStdOutOutputHandler(oBugId, sOutput):
    if gbDebugIO: fOutput("stdout>%s" % sOutput);
    asLog.append("stdout>%s" % sOutput);
  def fStdErrOutputHandler(oBugId, sOutput):
    if gbDebugIO: fOutput("stderr>%s" % sOutput);
    asLog.append("stderr>%s" % sOutput);
  def fLogMessageHandler(oBugId, sMessageClass, sMessage):
    if gbDebugIO: fOutput("log>%s: %s" % (sMessageClass, sMessage));
    asLog.append("log>%s: %s" % (sMessageClass, sMessage));
  def fApplicationStdOurOrErrOutputCallback(oBugId, uProcessId, sStdOutOrErr, sMessage):
    if gbDebugIO: fOutput("app:%d/0x%X:%s> %s" % (uProcessId, uProcessId, sStdOutOrErr, sMessage));
    asLog.append("app:%d/0x%X:%s> %s" % (uProcessId, uProcessId, sStdOutOrErr, sMessage));
  
  
  def fFailedToDebugApplicationHandler(oBugId, sErrorMessage):
    global gbTestFailed;
    if sExpectedFailedToDebugApplicationErrorMessage == sErrorMessage:
      return;
    gbTestFailed = True;
    if not gbDebugIO: 
      for sLine in asLog:
        fOutput(sLine);
    fOutput("- Failed test: %s" % sTestDescription);
    fOutput("  Expected:    %s" % repr(sExpectedFailedToDebugApplicationErrorMessage));
    fOutput("  Error:       %s" % repr(sErrorMessage));
    oBugId.fStop();
  
  def fInternalExceptionHandler(oBugId, oException, oTraceBack):
    global gbTestFailed;
    gbTestFailed = True;
    if not gbDebugIO: 
      for sLine in asLog:
        fOutput(sLine);
    fOutput("@" * 80);
    fOutput("- An internal exception has occured in test: %s" % sTestDescription);
    fOutput("  %s" % repr(oException));
    fOutput("  Stack:");
    txStack = traceback.extract_tb(oTraceBack);
    uFrameIndex = len(txStack) - 1;
    for (sFileName, uLineNumber, sFunctionName, sCode) in reversed(txStack):
      sSource = "%s/%d" % (sFileName, uLineNumber);
      if sFunctionName != "<module>":
        sSource = "%s (%s)" % (sFunctionName, sSource);
      fOutput("  %3d %s" % (uFrameIndex, sSource));
      if sCode:
        fOutput("      > %s" % sCode.strip());
      uFrameIndex -= 1;
    fOutput("@" * 80);
    oBugId.fStop();
  
  def fPageHeapNotEnabledHandler(oBugId, uProcessId, sBinaryName, sCommandLine, bPreventable):
    assert sBinaryName == "cmd.exe", \
        "It appears you have not enabled page heap for %s, which is required to run tests." % sBinaryName;
  
  def fFailedToApplyMemoryLimitsHandler(oBugId, uProcessId, sBinaryName, sCommandLine):
    global gbTestFailed;
    gbTestFailed = True;
    if not gbDebugIO: 
      for sLine in asLog:
        fOutput(sLine);
    fOutput("- Failed to apply memory limits to process %d/0x%X (%s: %s) for test: %s" % \
        (uProcessId, uProcessId, sBinaryName, sCommandLine, sTestDescription));
    oBugId.fStop();
  
  try:
    oBugId = cBugId(
      sCdbISA = sISA,
      sApplicationBinaryPath = sApplicationBinaryPath,
      asApplicationArguments = asApplicationArguments,
      asSymbolServerURLs = ["http://msdl.microsoft.com/download/symbols"], # Will be ignore if symbols are disabled.
      bGenerateReportHTML = gbGenerateReportHTML,
      uTotalMaxMemoryUse = guTotalMaxMemoryUse,
      fInternalExceptionCallback = fInternalExceptionHandler,
      fFailedToDebugApplicationCallback = sExpectedFailedToDebugApplicationErrorMessage and fFailedToDebugApplicationHandler,
      fFailedToApplyMemoryLimitsCallback = fFailedToApplyMemoryLimitsHandler, 
      fPageHeapNotEnabledCallback = fPageHeapNotEnabledHandler,
      fStdInInputCallback = fStdInInputHandler,
      fStdOutOutputCallback = fStdOutOutputHandler,
      fStdErrOutputCallback = fStdErrOutputHandler,
      fLogMessageCallback =  fLogMessageHandler,
      fApplicationStdOurOrErrOutputCallback = fApplicationStdOurOrErrOutputCallback,
    );
    oBugId.fStart();
    oBugId.fSetCheckForExcessiveCPUUsageTimeout(1);
    oBugId.fWait();
    if gbTestFailed:
      return;
    oBugReport = oBugId.oBugReport;
    if sExpectedFailedToDebugApplicationErrorMessage:
      fOutput("+ %s" % sTestDescription);
    elif sExpectedBugId:
      if not oBugReport:
        gbTestFailed = True;
        if not gbDebugIO: 
          for sLine in asLog:
            fOutput(sLine);
        fOutput("- Failed test: %s" % sTestDescription);
        fOutput("  Test should have reported a bug in the application.");
        fOutput("  Expected:    %s @ %s" % (sExpectedBugId, sExpectedBugLocation));
        fOutput("  Reported:    no bug");
      elif (
        (isinstance(sExpectedBugId, tuple) and oBugReport.sId in sExpectedBugId)
        or (isinstance(sExpectedBugId, str) and oBugReport.sId == sExpectedBugId)
      ) and (
        sExpectedBugLocation == oBugReport.sBugLocation
      ):
        fOutput("+ %s" % sTestDescription);
        if gbGenerateReportHTML:
          # We'd like a report file name base on the BugId, but the later may contain characters that are not valid in a file name
          sDesiredReportFileName = "%s %s @ %s.html" % (sPythonISA, oBugReport.sId, oBugReport.sBugLocation);
          # Thus, we need to translate these characters to create a valid filename that looks very similar to the BugId
          sValidReportFileName = mFileSystem.fsValidName(sDesiredReportFileName, bUnicode = False);
          mFileSystem.fWriteDataToFile(
            oBugReport.sReportHTML,
            sReportsFolderName,
            sValidReportFileName,
            fbRetryOnFailure = lambda: False,
          );
      else:
        gbTestFailed = True;
        if not gbDebugIO: 
          for sLine in asLog:
            fOutput(sLine);
        fOutput("- Failed test: %s" % sTestDescription);
        fOutput("  Test reported a different bug than expected in the application.");
        fOutput("  Expected:    %s @ %s" % (sExpectedBugId, sExpectedBugLocation));
        fOutput("  Reported:    %s @ %s" % (oBugReport.sId, oBugReport.sBugLocation));
        fOutput("               %s" % (oBugReport.sBugDescription));
    elif oBugReport:
      gbTestFailed = True;
      if not gbDebugIO: 
        for sLine in asLog:
          fOutput(sLine);
      fOutput("- Failed test: %s" % sTestDescription);
      fOutput("  Test reported an unexpected bug in the application.");
      fOutput("  Expected:    no bug");
      fOutput("  Reported:    %s @ %s" % (oBugReport.sId, oBugReport.sBugLocation));
      fOutput("               %s" % (oBugReport.sBugDescription));
    else:
      fOutput("+ %s" % sTestDescription);
    if gbDebugIO:
      fOutput();
      fOutput("=" * 80);
      fOutput();
  except Exception, oException:
    fOutput("- Failed test: %s" % sTestDescription);
    fOutput("  Expected:    %s @ %s" % (sExpectedBugId, sExpectedBugLocation));
    fOutput("  Exception:   %s" % repr(oException));
    raise;
  finally:
    if bDebugStartFinish:
      fOutput("* Finished %s" % sTestDescription);

if __name__ == "__main__":
  asArgs = sys.argv[1:];
  bQuickTestSuite = False;
  bFullTestSuite = False;
  while asArgs:
    if asArgs[0] == "--full": 
      bFullTestSuite = True;
      gbGenerateReportHTML = True;
    elif asArgs[0] == "--quick": 
      bQuickTestSuite = True;
    elif asArgs[0] == "--debug": 
      gbDebugIO = True;
      gbGenerateReportHTML = True;
    else:
      break;
    asArgs.pop(0);
  if asArgs:
    gbDebugIO = True; # Single test: output stdio
    gbGenerateReportHTML = True;
  nStartTime = time.clock();
  if asArgs:
    fOutput("* Starting test...");
    fTest(asArgs[0], asArgs[1:], None); # Expect no exceptions.
  else:
    fOutput("* Starting tests...");
    if not bFullTestSuite:
      # When we're not running the full test suite, we're not saving reports, so we don't need symbols.
      # Disabling symbols should speed things up considerably.
      cBugId.dxConfig["asDefaultSymbolServerURLs"] = None;
    # This will try to debug a non-existing application and check that the error thrown matches the expected value.
    fTest("x86",     None,                                                      None, \
        sApplicationBinaryPath = "<invalid>", \
        sExpectedFailedToDebugApplicationErrorMessage = "Unable to start a new process for binary \"<invalid>\".");
    fTest("x86",     None,                                                      None, \
        sApplicationBinaryPath = "does not exist", \
        sExpectedFailedToDebugApplicationErrorMessage = "Unable to start a new process for binary \"does not exist\".");
    for sISA in asTestISAs:
      fTest(sISA,    ["Nop"],                                                   None); # No exceptions, just a clean program exit.
      fTest(sISA,    ["Breakpoint"],                                            "Breakpoint ed2.531");
      if bQuickTestSuite:
        continue; # Just do a test without a crash and breakpoint.
      # This will run the test in a cmd shell, so the exception happens in a child process. This should not affect the outcome.
      fTest(sISA,    ["Breakpoint"],                                            "Breakpoint ed2.531",
            bRunInShell = True);
      fTest(sISA,    ["CPUUsage"],                                              "CPUUsage ed2.531");
      fTest(sISA,    ["C++"],                                                  ("C++ ed2.531",
                                                                                "C++:cException ed2.531"));
      fTest(sISA,    ["IntegerDivideByZero"],                                   "IntegerDivideByZero ed2.531");
# This test will throw a first chance integer overflow, but Visual Studio added an exception handler that then triggers
# another exception, so the report is incorrect.
#      fTest(sISA,    ["IntegerOverflow"],                                      "IntegerOverflow xxx.ed2");
      fTest(sISA,    ["Numbered", 0x41414141, 0x42424242],                      "0x41414141 ed2.531");
      fTest(sISA,    ["IllegalInstruction"],                                   ("IllegalInstruction f17.f17",
                                                                                "IllegalInstruction f17.ed2"),
          sExpectedBugLocationFunctionName = "fIllegalInstruction");
      fTest(sISA,    ["PrivilegedInstruction"],                                ("PrivilegedInstruction 0fc.0fc",
                                                                                "PrivilegedInstruction 0fc.ed2"),
          sExpectedBugLocationFunctionName = "fPrivilegedInstruction");
      fTest(sISA,    ["StackExhaustion", 0x100],                                "StackExhaustion ed2.531");
      fTest(sISA,    ["RecursiveCall", 2],                                      "RecursiveCall 950.6d1",
          sExpectedBugLocationFunctionName = "fStackRecursionFunction1");
      if bFullTestSuite:
        fTest(sISA,  ["RecursiveCall", 1],                                      "RecursiveCall 950",
          sExpectedBugLocationFunctionName = "fStackRecursionFunction1");
        fTest(sISA,  ["RecursiveCall", 3],                                      "RecursiveCall 950.4e9",
          sExpectedBugLocationFunctionName = "fStackRecursionFunction1");
        fTest(sISA,  ["RecursiveCall", 20],                                     "RecursiveCall 950.48b",
          sExpectedBugLocationFunctionName = "fStackRecursionFunction1");
      # A pure virtual function call should result in an AppExit exception. However, sometimes the "binary!purecall" or
      # "binary!_purecall" function can be found on the stack to destinguish these specific cases. Wether this works
      # depends on the build of the application and whether symbols are being used.
      fTest(sISA,    ["PureCall"],                                              "PureCall 12d.838",
          sExpectedBugLocationFunctionName = "fCallVirtual");
      fTest(sISA,    ["OOM", "HeapAlloc", guTotalMaxMemoryUse],                 "OOM ed2.531");
      fTest(sISA,    ["OOM", "C++", guTotalMaxMemoryUse],                       "OOM ed2.531");
      # WRT
      fTest(sISA,    ["WRTOriginate", 0x87654321, "message"],                   "Stowed[0x87654321] ed2.531");
      fTest(sISA,    ["WRTLanguage",  0x87654321, "message"],                   "Stowed[0x87654321@cIUnknown] ed2.531");
      # Double free
      fTest(sISA,    ["DoubleFree",                1],                          "DoubleFree[1] ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["DoubleFree",                2],                          "DoubleFree[2] ed2.531");
        fTest(sISA,  ["DoubleFree",                3],                          "DoubleFree[3] ed2.531");
        fTest(sISA,  ["DoubleFree",                4],                          "DoubleFree[4n] ed2.531");
        # Extra tests to check if the code deals correctly with memory areas too large to dump completely:
        uMax = cBugId.dxConfig["uMaxMemoryDumpSize"];
        fTest(sISA,  ["DoubleFree",             uMax],                          "DoubleFree[4n] ed2.531");
        fTest(sISA,  ["DoubleFree",         uMax + 1],                          "DoubleFree[4n+1] ed2.531");
        fTest(sISA,  ["DoubleFree",         uMax + 4],                          "DoubleFree[4n] ed2.531");
        
      # Misaligned free
      fTest(sISA,    ["MisalignedFree",            1,  1],                      "MisalignedFree[1]+0 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["MisalignedFree",            1,  2],                      "MisalignedFree[1]+1 ed2.531");
        fTest(sISA,  ["MisalignedFree",            2,  4],                      "MisalignedFree[2]+2 ed2.531");
        fTest(sISA,  ["MisalignedFree",            3,  6],                      "MisalignedFree[3]+3 ed2.531");
        fTest(sISA,  ["MisalignedFree",            4,  8],                      "MisalignedFree[4n]+4n ed2.531");
        fTest(sISA,  ["MisalignedFree",            5,  10],                     "MisalignedFree[4n+1]+4n+1 ed2.531");
        fTest(sISA,  ["MisalignedFree",            2,  1],                      "MisalignedFree[2]@1 ed2.531");
        fTest(sISA,  ["MisalignedFree",            3,  2],                      "MisalignedFree[3]@2 ed2.531");
        fTest(sISA,  ["MisalignedFree",            4,  3],                      "MisalignedFree[4n]@3 ed2.531");
        fTest(sISA,  ["MisalignedFree",            5,  4],                      "MisalignedFree[4n+1]@4n ed2.531");
        fTest(sISA,  ["MisalignedFree",            1,  -1],                     "MisalignedFree[1]-1 ed2.531");
        fTest(sISA,  ["MisalignedFree",            1,  -2],                     "MisalignedFree[1]-2 ed2.531");
        fTest(sISA,  ["MisalignedFree",            1,  -3],                     "MisalignedFree[1]-3 ed2.531");
        fTest(sISA,  ["MisalignedFree",            1,  -4],                     "MisalignedFree[1]-4n ed2.531");
        fTest(sISA,  ["MisalignedFree",            1,  -5],                     "MisalignedFree[1]-4n-1 ed2.531");
      # NULL pointers
      fTest(sISA,    ["AccessViolation",   "Read",     1],                      "AVR@NULL+1 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["AccessViolation",   "Read", 2],                          "AVR@NULL+2 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", 3],                          "AVR@NULL+3 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", 4],                          "AVR@NULL+4n ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", 5],                          "AVR@NULL+4n+1 ed2.531");
      uSignPadding = {"x86": 0, "x64": 0xFFFFFFFF00000000}[sISA];
      fTest(sISA,    ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFF],    "AVR@NULL-1 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFE],    "AVR@NULL-2 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFD],    "AVR@NULL-3 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFC],    "AVR@NULL-4n ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFB],    "AVR@NULL-4n-1 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFFA],    "AVR@NULL-4n-2 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFF9],    "AVR@NULL-4n-3 ed2.531");
        fTest(sISA,  ["AccessViolation",   "Read", uSignPadding+0xFFFFFFF8],    "AVR@NULL-4n ed2.531");
      # These are detected by Page Heap / Application Verifier
      fTest(sISA,    ["OutOfBounds", "Heap", "Write", 1, -1, 1],                "OOBW[1]-1~1 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", 2, -2, 2],                "OOBW[2]-2~2 ed2.531");
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", 3, -3, 3],                "OOBW[3]-3~3 ed2.531");
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", 4, -4, 4],                "OOBW[4n]-4n~4n ed2.531");
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", 5, -5, 5],                "OOBW[4n+1]-4n-1~4n+1 ed2.531");
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", 1, -4, 5],                "OOBW[1]-4n~4n ed2.531"); # Last byte written is within bounds!
        # Make sure very large allocations do not cause issues in cBugId
        fTest(sISA,  ["OutOfBounds", "Heap", "Write", guLargeHeapBlockSize, -4, 4], "OOBW[4n]-4n~4n ed2.531");
      # Page heap does not appear to work for x86 tests on x64 platform.
      fTest(sISA,    ["UseAfterFree", "Read",    1,  0],                        "UAFR[1]@0 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["UseAfterFree", "Write",   2,  1],                        "UAFW[2]@1 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    3,  2],                        "UAFR[3]@2 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   4,  3],                        "UAFW[4n]@3 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    5,  4],                        "UAFR[4n+1]@4n ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   6,  5],                        "UAFW[4n+2]@4n+1 ed2.531");
      fTest(sISA,    ["UseAfterFree", "Read",    1,  1],                        "OOBUAFR[1]+0 ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["UseAfterFree", "Write",   2,  3],                        "OOBUAFW[2]+1 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    3,  5],                        "OOBUAFR[3]+2 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   4,  7],                        "OOBUAFW[4n]+3 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    5,  9],                        "OOBUAFR[4n+1]+4n ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   6, 11],                        "OOBUAFW[4n+2]+4n+1 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    1, -1],                        "OOBUAFR[1]-1 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   1, -2],                        "OOBUAFW[1]-2 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    1, -3],                        "OOBUAFR[1]-3 ed2.531");
        fTest(sISA,  ["UseAfterFree", "Write",   1, -4],                        "OOBUAFW[1]-4n ed2.531");
        fTest(sISA,  ["UseAfterFree", "Read",    1, -5],                        "OOBUAFR[1]-4n-1 ed2.531");
      # These issues are not detected until they cause an access violation. Heap blocks may be aligned up to 0x10 bytes.
      fTest(sISA,    ["BufferOverrun",   "Heap", "Read",   0xC, 5],             "OOBR[4n]+4n ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["BufferOverrun",   "Heap", "Read",   0xD, 5],             "OOBR[4n+1]+3 ed2.531");
        fTest(sISA,  ["BufferOverrun",   "Heap", "Read",   0xE, 5],             "OOBR[4n+2]+2 ed2.531");
        fTest(sISA,  ["BufferOverrun",   "Heap", "Read",   0xF, 5],             "OOBR[4n+3]+1 ed2.531");
      # These issues are detected when they cause an access violation, but earlier OOBWs took place that did not cause AVs.
      # This is detected and reported by application verifier because the page heap suffix was modified.
      fTest(sISA,    ["BufferOverrun",   "Heap", "Write",  0xC, 5],             "OOBW[4n]+0~4n ed2.531");
      if bFullTestSuite:
        fTest(sISA,  ["BufferOverrun",   "Heap", "Write",  0xD, 5],             "OOBW[4n+1]+0~3 ed2.531");
        fTest(sISA,  ["BufferOverrun",   "Heap", "Write",  0xE, 5],             "OOBW[4n+2]+0~2 ed2.531");
        fTest(sISA,  ["BufferOverrun",   "Heap", "Write",  0xF, 5],             "OOBW[4n+3]+0~1 ed2.531");
        fTest(sISA,  ["BufferOverrun",   "Heap", "Write", 0x10, 5],             "OOBW[4n]+0 ed2.531"); # First byte writen causes AV; no data hash
      # Stack based heap overflows can cause an access violation if the run off the end of the stack, or a debugbreak
      # when they overwrite the stack cookie and the function returns. Finding out how much to write to overwrite the
      # stack cookie but not run off the end of the stack requires a bit of dark magic. I've only tested these values
      # on x64!
      uSmash = sISA == "x64" and 0x200 or 0x100;
      fTest(sISA,    ["BufferOverrun",  "Stack", "Write", 0x10, uSmash],        "OOBW@Stack ed2.531");
      # The OS does not allocate a guard page at the top of the stack. Subsequently, there may be a writable allocation
      # there, and a large enough stack overflow will write way past the end of the stack before causing an AV. This
      # causes a different BugId, so this test is not reliable at the moment.
      # TODO: Reimplement BugId and add feature that adds guard pages to all virtual allocations.
      # fTest(sISA,    ["BufferOverrun",  "Stack", "Write", 0x10, 0x100000],     "AVW[Stack]+0 ed2.531");
      
      if bFullTestSuite:
        for (uBaseAddress, sDescription) in [
          # 0123456789ABCDEF
                 (0x44444444, "Unallocated"), # Not sure if this is guaranteed, but in my experience it's reliable.
             (0x7ffffffdffff, "Unallocated"), # Highly unlikely to be allocated as it is at the very top of allocatable mem.
             (0x7ffffffe0000, "Reserved"),
             (0x7ffffffeffff, "Reserved"),
             (0x7fffffff0000, "Invalid"),
             (0x7fffffffffff, "Invalid"),
             (0x800000000000, "Invalid"),
         (0x8000000000000000, "Invalid"),
        ]:
          if uBaseAddress < (1 << 32) or sISA == "x64":
            # On x64, there are some limitations to exceptions occuring at addresses between the userland and kernelland
            # memory address ranges.
            fTest(sISA,  ["AccessViolation", "Read", uBaseAddress],             "AVR@%s ed2.531" % sDescription);
            if uBaseAddress >= 0x800000000000 and uBaseAddress < 0xffff800000000000:
              fTest(sISA,  ["AccessViolation", "Write", uBaseAddress],          "AV_@%s ed2.531" % sDescription);
              fTest(sISA,  ["AccessViolation", "Jump", uBaseAddress],           "AVE@%s 46f.46f" % sDescription,
                  sExpectedBugLocationFunctionName = "fJump");
            else:
              fTest(sISA,  ["AccessViolation", "Write", uBaseAddress],          "AVW@%s ed2.531" % sDescription);
              fTest(sISA,  ["AccessViolation", "Jump", uBaseAddress],           "AVE@%s 46f.ed2" % sDescription,
                  sExpectedBugLocationFunctionName = "fJump");
            fTest(sISA,    ["AccessViolation", "Call", uBaseAddress],          ("AVE@%s f47.f47" % sDescription,
                                                                                "AVE@%s f47.ed2" % sDescription),
                  sExpectedBugLocationFunctionName = "fCall");
      
      if bFullTestSuite:
        for (uBaseAddress, (sAddressId, sAddressDescription, sSecurityImpact)) in ddtsDetails_uSpecialAddress_sISA[sISA].items():
          if uBaseAddress < (1 << 32) or (sISA == "x64" and uBaseAddress < (1 << 47)):
            fTest(sISA,    ["AccessViolation", "Read", uBaseAddress],           "AVR@%s ed2.531" % sAddressId);
            if bFullTestSuite:
              fTest(sISA,  ["AccessViolation", "Write", uBaseAddress],          "AVW@%s ed2.531" % sAddressId);
              fTest(sISA,  ["AccessViolation", "Call", uBaseAddress],          ("AVE@%s f47.f47" % sAddressId,
                                                                                "AVE@%s f47.ed2" % sAddressId),
                  sExpectedBugLocationFunctionName = "fCall");
              fTest(sISA,  ["AccessViolation", "Jump", uBaseAddress],          ("AVE@%s 46f.46f" % sAddressId,
                                                                                "AVE@%s 46f.ed2" % sAddressId),
                  sExpectedBugLocationFunctionName = "fJump");
          elif sISA == "x64":
            fTest(sISA,    ["AccessViolation", "Read", uBaseAddress],           "AVR@%s ed2.531" % sAddressId);
            if bFullTestSuite:
              fTest(sISA,  ["AccessViolation", "Write", uBaseAddress],          "AV_@%s ed2.531" % sAddressId);
              fTest(sISA,  ["AccessViolation", "Call", uBaseAddress],          ("AVE@%s f47.f47" % sAddressId,
                                                                                "AVE@%s f47.ed2" % sAddressId),
                  sExpectedBugLocationFunctionName = "fCall");
              fTest(sISA,  ["AccessViolation", "Jump", uBaseAddress],          ("AVE@%s 46f.46f" % sAddressId,
                                                                                "AVE@%s 46f.ed2" % sAddressId),
                  sExpectedBugLocationFunctionName = "fJump");
  nTestTime = time.clock() - nStartTime;
  if gbTestFailed:
    fOutput("- Testing failed after %3.3f seconds" % nTestTime);
    sys.exit(1);
  else:
    fOutput("+ Testing completed in %3.3f seconds" % nTestTime);
    sys.exit(0);
