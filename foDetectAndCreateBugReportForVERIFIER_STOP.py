import re;
from cBugReport import cBugReport;
from cCorruptionDetector import cCorruptionDetector;
from cHeapAllocation import cHeapAllocation;
from fsGetNumberDescription import fsGetNumberDescription;
from ftuLimitedAndAlignedMemoryDumpStartAddressAndSize import ftuLimitedAndAlignedMemoryDumpStartAddressAndSize;
from sBlockHTMLTemplate import sBlockHTMLTemplate;

def foDetectAndCreateBugReportForVERIFIER_STOP(oCdbWrapper, uExceptionCode, asCdbOutput):
  uErrorNumber = None;
  uProcessId = None;
  sMessage = None;
  uVerifierStopHeapBlockAddress = None;
  uVerifierStopHeapBlockSize = None;
  uVerifierStopHeapBlockHandle = None; 
  uVerifierStopHeapHandle = None; # This is what is being used, which may differ from the actual heap handle of the block
  uCorruptedStamp = None;
  uCorruptionAddress = None;
  asRelevantLines = [];
  
  for sLine in asCdbOutput:
    # Ignore exmpty lines
    if not sLine:
      continue;
    # Look for the first VERIFIER STOP message and gather information
    if uErrorNumber is None:
      oErrorMessageMatch = re.match(r"^VERIFIER STOP ([0-9A-F]+): pid 0x([0-9A-F]+): (.*?)\s*$", sLine);
      if oErrorMessageMatch:
        sErrorNumber, sProcessId, sMessage = oErrorMessageMatch.groups();
        uErrorNumber = long(sErrorNumber, 16);
        uProcessId = long(sProcessId, 16);
        asRelevantLines.append(sLine);
        oCdbWrapper.fSelectProcess(uProcessId);
        assert uProcessId == oCdbWrapper.oCurrentProcess.uId, \
            "VERIFIER STOP in process with id %d/0x%X, but current process id is %d/0x%X" % \
            (uProcessId, uProcessId, oCdbWrapper.oCurrentProcess.uId, oCdbWrapper.oCurrentProcess.uId);
      continue;
    # A VERIFIER STOP message has been detected, gather what information verifier provides:
    oInformationMatch = re.match(r"^\t([0-9A-F]+) : (.*?)\s*$", sLine);
    if oInformationMatch:
      asRelevantLines.append(sLine);
      sValue, sDescription = oInformationMatch.groups();
      uValue = long(sValue, 16);
      sDescription = sDescription.lower(); # Both "Corruption address" and "corruption address" are used :(
      if sDescription == "heap block":
        uVerifierStopHeapBlockAddress = uValue;
      elif sDescription == "block size":
        uVerifierStopHeapBlockSize = uValue;
      elif sDescription == "corrupted stamp":
        uCorruptedStamp = uValue;
      elif sDescription == "corruption address":
        uCorruptionAddress = uValue;
      elif sDescription == "corruption address":
        uCorruptionAddress = uValue;
      elif sDescription == "heap handle":
        uVerifierStopHeapBlockHandle = uValue;
        uVerifierStopHeapHandle = uValue;
      elif sDescription == "heap used in the call":
        uVerifierStopHeapHandle = uValue;
      elif sDescription == "heap owning the block":
        uVerifierStopHeapBlockHandle = uValue;
    else:
      assert sLine.strip().replace("=", "") == "", \
          "Unknown VERIFIER STOP message line: %s\r\n%s" % (repr(sLine), "\r\n".join(asCdbOutput));
      break;
  else:
    assert uErrorNumber is None, \
        "Detected the start of a VERIFIER STOP message but not the end\r\n%s" % "\r\n".join(asCdbOutput);
    return None; # No VERIFIER STOP in the output.
  oCdbWrapper.fSelectProcess(uProcessId);
  oProcess = oCdbWrapper.oCurrentProcess;
  if uErrorNumber == 0x303:
    # |=======================================
    # |VERIFIER STOP 0000000000000303: pid 0xB2C: NULL handle passed as parameter. A valid handle must be used.
    # |
    # |0000000000000000 : Not used.
    # |0000000000000000 : Not used.
    # |0000000000000000 : Not used.
    # |0000000000000000 : Not used.
    # |
    # |=======================================
    return None; # This is a VERIFIER STOP, but not an interesting one and we can continue the application.
  
  assert uVerifierStopHeapBlockAddress is not None, \
      "The heap block start address was not found in the verifier stop message.\r\n%s" % "\r\n".join(asRelevantLines);
  assert uVerifierStopHeapBlockSize is not None, \
      "The heap block size was not found in the verifier stop message.\r\n%s" % "\r\n".join(asRelevantLines);
  
  if sMessage == "block already freed":
    # It appears there is a bug in verifier that causes it to report the wrong address: rather than the address
    # of the block that was already freed, it reports the address of some struct. Luckily it appears that this struct
    # does contain the address of the heap block:
    #   PVOID pUnknown_0
    #   PVOID pUnknown_1
    #   PVOID pUnknown_2
    #   PVOID pUnknown_3
    #   PVOID pHeapBlock;  // A pointer to the start of the heap block.
    #   PVOID pVitualAllocation;  // A pointer to the virtual allocation that contains the heap block and page heap data.
    #   ULONG uVirtualAllocationSize;  // The size of the virtual allocations for the heap block and guard page.
    #   PVOID pUnknown_7;
    #   ULONG uHeapBlockSize; // The size of the heap block
    # This means we can read the address of the heap block by reading a pointer sized value at offset 4 * sizeof(PVOID).
    puHeapBlockAddress = uVerifierStopHeapBlockAddress + 4 * oProcess.uPointerSize;
    uHeapBlockAddress = oProcess.fuGetValue(
      "poi(0x%X)" % puHeapBlockAddress,
      "Get heap block address from verifier data"
    );
  else:
    # In all other cases, we trust verifier to provide the correct value:
    uHeapBlockAddress = uVerifierStopHeapBlockAddress;
  oHeapAllocation = oProcess.foGetHeapAllocationForAddressAndSize(uHeapBlockAddress, uVerifierStopHeapBlockSize);
  assert oHeapAllocation, \
      "No page heap report avaiable for address 0x%X" % uHeapBlockAddress;
  
  uMemoryDumpStartAddress = None;
  atxMemoryRemarks = [];
  if sMessage == "corrupted start stamp" and uCorruptedStamp == 0xABCDBBBA and not oHeapAllocation.oVirtualAllocation.bReserved:
    # Verifier sometimes reports this and I am not sure what is going on. Page heap will report that the heap block was
    # freed by the current function on the stack, while verifier reports this error almost immediately after that (from
    # that same stack). However, the start stamp reported in the verifier error is a valid value indicating the memory
    # was freed, so it makes no sense that it is reported as being corrupt. Also, there is no memory allocated at the
    # given address; it is only reserved, so it cannot actually contain a value.
    # I cannot think of any situation in which all this information is correct, and I suspect that verifier is
    # reporting the wrong kind of error. However, I have been unable to find a reliable repro for this to debug, so I
    # do not know exactly what is going on and what to report...
    (sHeapBlockAndOffsetId, sHeapBlockAndOffsetDescription) = \
        oHeapAllocation.ftsGetIdAndDescriptionForAddress(uVerifierStopHeapBlockAddress);
    sBugTypeId = "UnknownVerifierError%s" % sHeapBlockAndOffsetId;
    sBugDescription = "Application verifier reported a corrupt memory block, but no memory is allocated at the " \
        "address provided. This suggests that the verfier report is incorrect. However, it is likely that the " \
        "application does have some kind of memory corruption bug that triggers this report, but it is unknown " \
        "what kind of bug that might be. If you can reliably reproduce this, please contact the author of BugId " \
        "so this situation can be analyzed and BugId can be improved to report something more helpful here.";
    sSecurityImpact = "Unknown: this type of bug has not been analyzed before";
    if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block near 0x%X" % uVerifierStopHeapBlockAddress;
  elif sMessage in ["corrupted start stamp", "corrupted end stamp"] \
      and oHeapAllocation.uBlockStartAddress != uVerifierStopHeapBlockAddress:
    # When the application attempts to free (heap pointer + offset), Verifier does not detect this and will assume
    # the application provided pointer is correct. This causes it to look for the start and end stamp in the wrong
    # location and report this bug as memory corruption. When the page heap data shows no signs of corruption, we
    # can special case it.
    (sHeapBlockAndOffsetId, sHeapBlockAndOffsetDescription) = \
        oHeapAllocation.ftsGetIdAndDescriptionForAddress(uVerifierStopHeapBlockAddress);
    sBugTypeId = "MisalignedFree%s" % sHeapBlockAndOffsetId;
    sBugDescription = "The application attempted to free memory using a pointer that was %s." % sHeapBlockAndOffsetDescription;
    sSecurityImpact = "Unknown: this type of bug has not been analyzed before";
    if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block near 0x%X" % uVerifierStopHeapBlockAddress;
  elif sMessage == "block already freed":
    # |===========================================================
    # |VERIFIER STOP 00000007: pid 0x1358: block already freed
    # |
    # |        02F71000 : Heap handle
    # |        152F016C : Heap block
    # |        000004C8 : Block size
    # |        00000000 :
    # |===========================================================
    # |This verifier stop is not continuable. Process will be terminated
    # |when you use the `go' debugger command.
    # |===========================================================
    if oHeapAllocation.uBlockSize is None:
      sBugTypeId = "DoubleFree[?]";
      sBugDescription = "The application attempted to free a heap block of unknown size at address 0x%X twice" % \
          (uVerifierStopHeapBlockAddress);
      if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block near 0x%X" % uVerifierStopHeapBlockAddress;
    else:
      sBugTypeId = "DoubleFree[%s]" % fsGetNumberDescription(oHeapAllocation.uBlockSize);
      sBugDescription = "The application attempted to free a %d/0x%X byte heap block at address 0x%X twice" % \
          (oHeapAllocation.uBlockSize, oHeapAllocation.uBlockSize, oHeapAllocation.uBlockStartAddress);
      if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block at 0x%X" % oHeapAllocation.uBlockStartAddress;
    sSecurityImpact = "Potentially exploitable security issue, if the attacker can force the application to " \
        "allocate memory between the two frees";
  elif sMessage == "corrupted heap pointer or using wrong heap":
    # |===========================================================
    # |VERIFIER STOP 00000006: pid 0x144C: corrupted heap pointer or using wrong heap 
    # |
    # |        077F1000 : Heap used in the call
    # |        43742FE0 : Heap block
    # |        00000020 : Block size
    # |        277F1000 : Heap owning the block
    # |===========================================================
    # |This verifier stop is not continuable. Process will be terminated 
    # |when you use the `go' debugger command.
    # |===========================================================
    assert uVerifierStopHeapHandle is not None, \
        "Missing 'Heap used in the call' value in the VERIFIER STOP message.\r\n%s" % "\r\n".join(asCdbOutput);
    assert uVerifierStopHeapBlockHandle is not None, \
        "Missing 'Heap owning the block' value in the VERIFIER STOP message.\r\n%s" % "\r\n".join(asCdbOutput);
    if oHeapAllocation.uBlockSize is None:
      sBugTypeId = "IncorrectHeap[?]";
      sBugDescription = "The application provided an incorrect heap handle (0x%X) for a heap block of unknown size " \
          "near address 0x%X which belongs to another heap (handle 0x%X)" % \
          (uVerifierStopHeapHandle, uVerifierStopHeapBlockAddress, uVerifierStopHeapBlockHandle);
      if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block near 0x%X" % uVerifierStopHeapBlockAddress;
    else:
      sBugTypeId = "IncorrectHeap[%s]" % (fsGetNumberDescription(oHeapAllocation.uBlockSize));
      sBugDescription = "The application provided an incorrect heap handle (0x%X) for a %d/0x%X byte heap block at " \
          "address 0x%X which belongs to another heap (handle 0x%X)" % \
          (uVerifierStopHeapHandle, oHeapAllocation.uBlockSize, oHeapAllocation.uBlockSize, \
          oHeapAllocation.uBlockStartAddress, uVerifierStopHeapBlockHandle);
      if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
        sCdbHeapHTMLOutputHeader = "Heap information for block at 0x%X" % oHeapAllocation.uBlockStartAddress;
    sSecurityImpact = "Unknown: this type of bug has not been analyzed before";
  else:
    # Check the page heap data near the heap block for signs of corruption:
    oCorruptionDetector = cCorruptionDetector.foCreateForHeapAllocation(oHeapAllocation);
    
    if oCdbWrapper.bGenerateReportHTML:
      uMemoryDumpStartAddress = oHeapAllocation.uBlockStartAddress;
      uMemoryDumpSize = oHeapAllocation.uBlockSize;
      if oHeapAllocation:
        atxMemoryRemarks.extend(oHeapAllocation.fatxMemoryRemarks());
  
    # Handle various VERIFIER STOP messages.
    if sMessage in ["corrupted start stamp", "corrupted end stamp"]:
      assert uCorruptionAddress is None, \
          "We do not expect the corruption address to be provided in this VERIFIER STOP message\r\n%s" % \
              "\r\n".join(asRelevantLines);
      sBugTypeId = "OOBW";
      uCorruptionStartAddress = sMessage == "corrupted start stamp" \
          and oHeapAllocation.uStartStampAddress \
          or oHeapAllocation.uEndStampAddress;
      uCorruptionEndAddress = uCorruptionStartAddress + 4; # Stamps are 4 bytes
    elif sMessage in ["corrupted suffix pattern", "corrupted header"]:
      assert uCorruptionAddress is not None, \
          "The corruption address is expected to be provided in this VERIFIER STOP message:\r\n%s" % \
              "\r\n".join(asRelevantLines);
      # Page heap stores the heap as close as possible to the edge of a page, taking into account that the start of the
      # heap block must be properly aligned. Bytes between the heap block and the end of the page are initialized to
      # 0xD0. Verifier has detected that one of the bytes changed value, which indicates an out-of-bounds write. BugId
      # will try to find all bytes that were changed:
      sBugTypeId = "OOBW";
      uCorruptionStartAddress = uCorruptionAddress;
      uCorruptionEndAddress = uCorruptionStartAddress + 1; # We do not know the size, so assume one byte.
    elif sMessage == "corrupted infix pattern":
      assert uCorruptionAddress is not None, \
          "The corruption address is expected to be provided in the VERIFIER STOP message:\r\n%s" % \
              "\r\n".join(asRelevantLines);
      # Page heap sometimes does not free a heap block immediately, but overwrites the bytes with 0xF0. Verifier has
      # detected that one of the bytes changed value, which indicates a write-after-free. BugId will try to find all
      # bytes that were changed:
      oCorruptionDetector.fbDetectCorruption(
        oHeapAllocation.uBlockStartAddress, [0xF0 for x in xrange(oHeapAllocation.uBlockSize)]        );
      uCorruptionStartAddress = uCorruptionAddress;
      uCorruptionEndAddress = uCorruptionStartAddress + 1; # We do not know the size, so assume one byte.
      sBugTypeId = "UAFW";
    else:
      raise AssertionError("Unhandled VERIFIER STOP message: %s" % sMessage);
    # If we detected the reported corruption ourselves, we can get a better idea of the start and end address:
    # (One might expect that when a VERIFIER STOP reported memory corruption, we can always detect this as well, but
    # unfortunately, this is not always true. I do not know why a VERIFIER STOP would report corruption when there is
    # no sign of it, but by trusting it is correct, we at least get a report so I can find out what is going on).
    if oCorruptionDetector.bCorruptionDetected:
      uCorruptionStartAddress = oCorruptionDetector.uCorruptionStartAddress;
      uCorruptionEndAddress = oCorruptionDetector.uCorruptionEndAddress;
      if oCdbWrapper.bGenerateReportHTML:
        atxMemoryRemarks.extend(oCorruptionDetector.fatxMemoryRemarks());
    uCorruptionSize = uCorruptionEndAddress - uCorruptionStartAddress;
    
    # If the corruption starts before or ends after the heap block, expand the memory dump to include the entire
    # corrupted region.
    if oCdbWrapper.bGenerateReportHTML:
      if uCorruptionStartAddress < uMemoryDumpStartAddress:
        uMemoryDumpSize += uMemoryDumpStartAddress - uCorruptionStartAddress;
        uMemoryDumpStartAddress = uCorruptionStartAddress;
      if uCorruptionEndAddress < uMemoryDumpStartAddress + uMemoryDumpSize:
        uMemoryDumpSize += uCorruptionEndAddress - (uMemoryDumpStartAddress + uMemoryDumpSize);
      # Limit memory dump size
      uMemoryDumpStartAddress, uMemoryDumpSize = ftuLimitedAndAlignedMemoryDumpStartAddressAndSize(
        uMemoryDumpStartAddress, oProcess.uPointerSize, uMemoryDumpStartAddress, uMemoryDumpSize
      );
    # Get a human readable description of the start offset of corruption relative to the heap block, where corruption
    # starting before or inside the heap block will be relative to the start, and corruption after it to the end.
    (sHeapBlockAndOffsetId, sHeapBlockAndOffsetDescription) = \
        oHeapAllocation.ftsGetIdAndDescriptionForAddress(uCorruptionStartAddress); 
    sBugTypeId += sHeapBlockAndOffsetId;
    sBugDescription = "Page heap detected heap corruption at 0x%X; %s." % (uCorruptionStartAddress, sHeapBlockAndOffsetDescription);
    if uCorruptionStartAddress == oHeapAllocation.uBlockEndAddress:
      sBugDescription += " This appears to be a classic buffer-overrun vulnerability.";
      sSecurityImpact = "Potentially highly exploitable security issue.";
    else:
      sSecurityImpact = "Potentially exploitable security issue, if the corruption is attacker controlled.";
    # If we detected corruption by scanning certain bytes in the applications memory, make sure this matches what
    # verifier reported and save all bytes that were affected: so far, we only saved the bytes that had an unexpected
    # value, but there is a chance that a byte was overwritten with the same value it has before, in which case it was
    # not saved. This can be detect if it is surrounded by bytes that did change value. This code reads the value of all
    # bytes between the first and last byte that we detected was corrupted:
    if oCorruptionDetector.bCorruptionDetected:
      asCorruptedBytes = oCorruptionDetector.fasCorruptedBytes();
      sBugDescription += " The following byte values were written to the corrupted area: %s." % ", ".join(asCorruptedBytes);
      sBugTypeId += oCorruptionDetector.fsCorruptionId() or "";
    if oCdbWrapper.bGenerateReportHTML and oHeapAllocation:
      sCdbHeapHTMLOutputHeader = "Heap information for block near 0x%X" % uCorruptionStartAddress;
  
  oBugReport = cBugReport.foCreate(oProcess, sBugTypeId, sBugDescription, sSecurityImpact);
  if oCdbWrapper.bGenerateReportHTML:
    if uMemoryDumpStartAddress:
      oBugReport.fAddMemoryDump(
        uMemoryDumpStartAddress,
        uMemoryDumpStartAddress + uMemoryDumpSize,
        "Memory near heap block at 0x%X" % uMemoryDumpStartAddress,
      );
    oBugReport.atxMemoryRemarks.extend(atxMemoryRemarks);
  # Output the VERIFIER STOP message for reference
  if oCdbWrapper.bGenerateReportHTML:
    sVerifierStopMessageHTML = sBlockHTMLTemplate % {
      "sName": "VERIFIER STOP message",
      "sCollapsed": "Collapsed",
      "sContent": "<pre>%s</pre>" % "\r\n".join([
        oCdbWrapper.fsHTMLEncode(s, uTabStop = 8) for s in asRelevantLines
      ])
    };
    oBugReport.asExceptionSpecificBlocksHTML.append(sVerifierStopMessageHTML);
    # Output the page heap information for reference
    if oHeapAllocation:
      sCdbHeapOutputHTML = sBlockHTMLTemplate % {
        "sName": sCdbHeapHTMLOutputHeader,
        "sCollapsed": "Collapsed",
        "sContent": "<pre>%s</pre>" % "\r\n".join([
          oCdbWrapper.fsHTMLEncode(s, uTabStop = 8) for s in oHeapAllocation.asCdbHeapOutput
        ])
      };
      oBugReport.asExceptionSpecificBlocksHTML.append(sCdbHeapOutputHTML);
  
  oBugReport.bRegistersRelevant = False;
  return oBugReport;