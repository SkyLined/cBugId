from .fbIgnoreAccessViolationException import fbIgnoreAccessViolationException;

def fbUpdateReportForUnallocatedPointer(
  oCdbWrapper, oBugReport, oProcess, oThread, sViolationTypeId, uAccessViolationAddress, sViolationVerb, oVirtualAllocation
):
  if not oVirtualAllocation.bFree:
    return False;
  # No memory is allocated in this area
  oBugReport.sBugTypeId = "AV%s:Unallocated" % sViolationTypeId;
  oBugReport.sBugDescription = "An Access Violation exception happend at 0x%X while attempting to %s unallocated memory at 0x%X." % \
      (uAccessViolationAddress, sViolationVerb, uAccessViolationAddress);
  oBugReport.sSecurityImpact = "Potentially exploitable security issue, if the address can be controlled, or memory be allocated at the address.";
  oCdbWrapper.oCollateralBugHandler.fSetIgnoreExceptionFunction(lambda oCollateralBugHandler:
    fbIgnoreAccessViolationException(oCollateralBugHandler, oCdbWrapper, oProcess, oThread, sViolationTypeId)
  );
  return True;
