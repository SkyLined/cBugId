from cCorruptionDetector import cCorruptionDetector;
from fsGetNumberDescription import fsGetNumberDescription;
from ftuLimitedAndAlignedMemoryDumpStartAddressAndSize import ftuLimitedAndAlignedMemoryDumpStartAddressAndSize;

def fSetBugReportPropertiesForAccessViolationUsingHeapAllocation(
  oBugReport,
  uAccessViolationAddress, sViolationTypeId, sViolationTypeDescription,
  oHeapAllocation,
  uPointerSize, bGenerateReportHTML,
):
  if oHeapAllocation.uBlockStartAddress is not None and oHeapAllocation.uBlockSize is not None:
    if bGenerateReportHTML:
      uMemoryDumpStartAddress = oHeapAllocation.uBlockStartAddress;
      uMemoryDumpSize = oHeapAllocation.uBlockSize;
    if bGenerateReportHTML:
      if uAccessViolationAddress < oHeapAllocation.uBlockStartAddress:
        uPrefix = oHeapAllocation.uBlockStartAddress - uAccessViolationAddress;
        uMemoryDumpStartAddress -= uPrefix;
        uMemoryDumpSize += uPrefix;
        # If the memory dump because too large, truncate it.
        if uMemoryDumpSize > 0x1000:
          uMemoryDumpSize = 0x1000;
      elif uAccessViolationAddress >= oHeapAllocation.uBlockEndAddress:
        uPostFix = uAccessViolationAddress - oHeapAllocation.uBlockEndAddress + 1;
        # Show some of the guard page so we can insert labels where the AV took place, but only
        # if this does not cause the memory dump to become too large.
        if uMemoryDumpSize + uPostFix < 0x1000:
          uMemoryDumpSize += uPostFix;
      # Check if we're not trying to dump a rediculous amount of memory:
      # Clamp start and end address
      uMemoryDumpStartAddress, uMemoryDumpSize = ftuLimitedAndAlignedMemoryDumpStartAddressAndSize(
        uAccessViolationAddress, uPointerSize, uMemoryDumpStartAddress, uMemoryDumpSize
      );
      oBugReport.fAddMemoryDump(
        uMemoryDumpStartAddress,
        uMemoryDumpStartAddress + uMemoryDumpSize,
        "Memory near access violation at 0x%X" % uAccessViolationAddress,
      );
    bOutOfBounds = (uAccessViolationAddress < oHeapAllocation.uBlockStartAddress) \
                or (uAccessViolationAddress >= oHeapAllocation.uBlockEndAddress);
  else:
    assert oHeapAllocation.bFreed, \
        "If the page was not freed, we should be able to find the start and size of the heap block!!";
    # If the access was outside of the allocation, it was out of bounds, otherwise we can't be sure since we do not
    # know where the block was inside the allocation. Let's assume it was ok and only report UAF in such cases.
    bOutOfBounds = (uAccessViolationAddress < oHeapAllocation.uAllocationStartAddress) \
                or (uAccessViolationAddress >= oHeapAllocation.uAllocationEndAddress);
  (sHeapBlockAndOffsetId, sHeapBlockAndOffsetDescription) = \
      oHeapAllocation.ftsGetIdAndDescriptionForAddress(uAccessViolationAddress);
  
  oBugReport.sBugDescription = "Access violation while %s %smemory at 0x%X; %s." % (sViolationTypeDescription, \
      oHeapAllocation.bFreed and "freed " or "", uAccessViolationAddress, sHeapBlockAndOffsetDescription);
  sPotentialRisk = {
    "R": "might allow information disclosure and (less likely) arbitrary code execution",
    "W": "indicates arbitrary code execution may be possible",
    "E": "indicates arbitrary code execution is very likely possible",
  }[sViolationTypeId];
  oBugReport.sSecurityImpact = "Potentially exploitable security issue that %s." % sPotentialRisk;
  if oHeapAllocation.bFreed:
    # --- (OOB)UAF -----------------------------------------------------------
    # We do not expect to see corruption of the page heap struct, as this should have been detected when the memory was
    # freed. The code may have tried to access data outside the bounds of the freed memory (double face-palm!).
    oBugReport.sBugTypeId = "UAF%s%s" % (sViolationTypeId, sHeapBlockAndOffsetId);
    oBugReport.sBugDescription += " This indicates a Use-After-Free (UAF) bug was triggered.";
    if bOutOfBounds:
      oBugReport.sBugTypeId = "OOB" + oBugReport.sBugTypeId;
      oBugReport.sBugDescription += " In addition, the code attempted to access data Out-Of-Bounds (OOB).";
    return;
  
  if bOutOfBounds:
    oBugReport.sBugTypeId = "OOB%s%s" % (sViolationTypeId, sHeapBlockAndOffsetId);
    oBugReport.sBugDescription += " This indicates an Out-Of-Bounds (OOB) access bug was triggered.";
  else:
    # TODO: add heap block access rights description!
    oBugReport.sBugTypeId = "AV%s%s" % (sViolationTypeId, sHeapBlockAndOffsetId);
    oBugReport.sBugDescription += " suggests an earlier memory corruption has corrupted a pointer, index or offset.";
  # We can check the page heap structures for signs of corruption to detect earlier out-of-bounds writes that did not
  # cause an access violation.
  oCorruptionDetector = cCorruptionDetector.foCreateForHeapAllocation(oHeapAllocation);
  if oCorruptionDetector.bCorruptionDetected:
    # We detected a modified byte; there was an OOB write before the one that caused this access
    # violation. Use it's offset instead and add this fact to the description.
    if bGenerateReportHTML:
      oBugReport.atxMemoryRemarks.extend(oCorruptionDetector.fatxMemoryRemarks());
    uCorruptionStartAddress = oCorruptionDetector.uCorruptionStartAddress;
    (sHeapBlockAndOffsetId, sHeapBlockAndOffsetDescription) = \
        oHeapAllocation.ftsGetIdAndDescriptionForAddress(uCorruptionStartAddress);
    # sHeapBlockAndOffsetDescription ^^^ is discarded because it repeats the heap block size, which is already mentioned
    # in oBugReport.sBugDescription
    if uCorruptionStartAddress <= oHeapAllocation.uBlockStartAddress:
      uOffsetBeforeStartOfBlock = oHeapAllocation.uBlockStartAddress - uCorruptionStartAddress;
      oBugReport.sBugDescription += (
        " An earlier out-of-bounds write was detected at 0x%X, %d/0x%X bytes " \
        "before that block because it modified the page heap prefix pattern."
      ) % (uCorruptionStartAddress, uOffsetBeforeStartOfBlock, uOffsetBeforeStartOfBlock);
    elif uCorruptionStartAddress >= oHeapAllocation.uBlockEndAddress:
      uOffsetBeyondEndOfBlock = uCorruptionStartAddress - oHeapAllocation.uBlockEndAddress;
      oBugReport.sBugDescription += (
        " An earlier out-of-bounds write was detected at 0x%X, %d/0x%X bytes " \
        "beyond that block because it modified the page heap suffix pattern."
      ) % (uCorruptionStartAddress, uOffsetBeyondEndOfBlock, uOffsetBeyondEndOfBlock);
    if uCorruptionStartAddress == oHeapAllocation.uBlockEndAddress:
      if sViolationTypeId == "R":
        oBugReport.sBugDescription += " This appears to be a classic linear read beyond the end of a buffer.";
        sSecurityImpact = "Potentially highly exploitable security issue that might allow information disclosure.";
      else:
        oBugReport.sBugDescription += " This appears to be a classic linear buffer-overrun vulnerability.";
        sSecurityImpact = "Potentially highly exploitable security issue that might allow arbitrary code execution.";
    asCorruptedBytes = oCorruptionDetector.fasCorruptedBytes();
    oBugReport.sBugDescription += " The following byte values were written to the corrupted area: %s." % \
        ", ".join(asCorruptedBytes);
    oBugReport.sBugTypeId = "OOBW%s%s" % (sHeapBlockAndOffsetId, oCorruptionDetector.fsCorruptionId());
    return;
  # --- OOB ---------------------------------------------------------------------
  # An out-of-bounds read on a page heap block that is allocated and has padding that happens in the padding or
  # immediately following it could be the result of sequentially reading an array. This means there may have been
  # earlier out-of-bounds reads that did not trigger an access violation:
  if sViolationTypeId == "R" \
    and oHeapAllocation.bPageHeap \
    and oHeapAllocation.bAllocated \
    and oHeapAllocation.uBlockEndAddress < oHeapAllocation.uAllocationEndAddress \
    and uAccessViolationAddress >= oHeapAllocation.uBlockEndAddress \
    and uAccessViolationAddress <= oHeapAllocation.uAllocationEndAddress:
    oBugReport.sBugDescription += " An earlier out-of-bounds read before this address may have happened without " \
          "having triggered an access violation.";

