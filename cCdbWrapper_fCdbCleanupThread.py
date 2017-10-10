from cBugReport_CdbTerminatedUnexpectedly import cBugReport_CdbTerminatedUnexpectedly;
from mWindowsAPI import fbTerminateProcessForId;

def cCdbWrapper_fCdbCleanupThread(oCdbWrapper):
  # wait for debugger thread to terminate.
  oCdbWrapper.oCdbStdInOutThread.join();
  # wait for stderr thread to terminate.
  oCdbWrapper.oCdbStdErrThread.join();
  # Terminate the cdb process in case it somehow is still running.
  try:
    oCdbWrapper.oCdbProcess.terminate();
  except:
    pass; # Apparently it wasn't running.
  # Make sure all stdio pipes are closed.
  try:
    oCdbWrapper.oCdbProcess.stdout.close();
  except:
    pass; # Apparently it wasn't open.
  try:
    oCdbWrapper.oCdbProcess.stderr.close();
  except:
    pass; # Apparently it wasn't open.
  try:
    oCdbWrapper.oCdbProcess.stdin.close();
  except:
    pass; # Apparently it wasn't open.
  # Wait for the cdb process to terminate
  uExitCode = oCdbWrapper.oCdbProcess.wait();
  # Destroy the subprocess object to make even more sure all stdio pipes are closed.
  del oCdbWrapper.oCdbProcess;
  # Determine if the debugger was terminated or if the application terminated. If not, an exception is thrown later, as
  # the debugger was not expected to stop, which is an unexpected error.
  bTerminationWasExpected = oCdbWrapper.bCdbWasTerminatedOnPurpose or len(oCdbWrapper.doProcess_by_uId) == 0;
  # There have also been cases where processes associated with an application were still running after this point in
  # the code. I have been unable to determine how this could happen but in an attempt to fix this, all process ids that
  # should be terminated are killed until they are confirmed they have terminated:
  if len(oCdbWrapper.doProcess_by_uId) > 0:
    for uProcessId in oCdbWrapper.doProcess_by_uId:
      fbTerminateProcessForId(uProcessId);
  if not bTerminationWasExpected:
    oCdbWrapper.oBugReport = cBugReport_CdbTerminatedUnexpectedly(oCdbWrapper, uExitCode);
  if oCdbWrapper.fFinishedCallback:
    oCdbWrapper.fFinishedCallback(oCdbWrapper.oBugReport);


