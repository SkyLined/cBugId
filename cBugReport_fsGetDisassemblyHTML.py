import re;
from dxConfig import dxConfig;

def fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, sLine, bImportant = False):
  # If this line starts with an address and opcode, make those semi-transparent.
  oMatch = re.match(r"^([0-9a-fA-F`]+\s+)([0-9a-fA-F]+\s+)(.+)$", sLine);
  if oMatch:
    sAddress, sOpcode, sInstruction = oMatch.groups();
    return "".join([
      "<span class=\"DisassemblyAddress\">%s</span>" % oCdbWrapper.fsHTMLEncode(sAddress),
      "<span class=\"DisassemblyOpcode\">%s</span>" % oCdbWrapper.fsHTMLEncode(sOpcode),
      "<span class=\"DisassemblyInstruction%s\">%s</span>" % \
          (bImportant and " Important" or "", oCdbWrapper.fsHTMLEncode(sInstruction)),
    ]);
  return "<span class=\"DisassemblyInformation\">%s</span>" % oCdbWrapper.fsHTMLEncode(sLine, uTabStop = 8);
  
def cBugReport_fsGetDisassemblyHTML(oBugReport, uAddress, sBeforeAddressInstructionDescription = None, sAtAddressInstructionDescription = None):
  oProcess = oBugReport.oProcess;
  oCdbWrapper = oProcess.oCdbWrapper;
  # See dxConfig.py for a description of these "magic" values.
  uDisassemblyBytesBefore = \
      dxConfig["uDisassemblyInstructionsBefore"] \
      * dxConfig["uDisassemblyAverageInstructionSize"] \
      + dxConfig["uDisassemblyAlignmentBytes"];
  uDisassemblyBytesAfter = \
      dxConfig["uDisassemblyInstructionsAfter"] \
      * dxConfig["uDisassemblyAverageInstructionSize"];
  # Get disassembly around code in which exception happened. This may not be possible if the instruction pointer points to unmapped memory.
  asHTML = [];
  if uDisassemblyBytesBefore > 0:
    # Get disassembly before address
    uStartAddress = uAddress - uDisassemblyBytesBefore;
    # Note: cannot use "u {address} L{length}" as length is number of instructions, and we want number of bytes. 
    asBeforeDisassembly = oProcess.fasExecuteCdbCommand(
      sCommand = ".if ($vvalid(0x%X, 0x%X)) { u 0x%X 0x%X; };" % \
          (uStartAddress, uDisassemblyBytesBefore, uStartAddress, uAddress - 1),
      sComment = "disassemble before address 0x%X" % uAddress,
      bOutputIsInformative = True,
    );
    # Limit number of instructions
    asBeforeDisassembly = asBeforeDisassembly[-dxConfig["uDisassemblyInstructionsBefore"]:];
    if asBeforeDisassembly:
      # Optionally highlight and describe instruction before the address:
      if sBeforeAddressInstructionDescription:
        sBeforeAddressDisassembly = asBeforeDisassembly.pop(-1);
      asHTML += [fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, s) for s in asBeforeDisassembly];
      if sBeforeAddressInstructionDescription:
        asHTML.append(
          "%s <span class=\"Important\">// %s</span>" % \
              (fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, sBeforeAddressDisassembly, bImportant = True), \
              sBeforeAddressInstructionDescription)
        );
  if uDisassemblyBytesAfter > 0:
    asAddressAtAndAfterDisassembly = oProcess.fasExecuteCdbCommand(
      sCommand = ".if ($vvalid(0x%X, 0x%X)) { u 0x%X L0x%X; };" % \
          (uAddress, uDisassemblyBytesAfter, uAddress, uDisassemblyBytesAfter),
      sComment = "Disassemble after address 0x%X" % uAddress, 
      bOutputIsInformative = True,
    );
    if asAddressAtAndAfterDisassembly:
      assert len(asAddressAtAndAfterDisassembly) >= 2, \
          "Unexpected short disassembly output:\r\n%s" % "\r\n".join(asAddressAtAndAfterDisassembly);
      # The first line contains the address of the instruction
      if not asHTML:
        asHTML.append("(prior disassembly not possible)");
      # disassembly starts with a line containing the address/symbol:
      sAddressLine = asAddressAtAndAfterDisassembly.pop(0);
      asHTML.append(fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, sAddressLine));
      # First line of disassembly at address is important;
      sAtAddressDisassembly = asAddressAtAndAfterDisassembly.pop(0);
      sAtAddressDisassemblyHTML = fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, sAtAddressDisassembly, bImportant = True);
      if sAtAddressInstructionDescription:
        sAtAddressDisassemblyHTML += " <span class=\"Important\">// %s</span>" % sAtAddressInstructionDescription;
      asHTML.append(sAtAddressDisassemblyHTML);
      # Limit the number of instructions, taking into account we already processed one:
      asAfterDisassembly = asAddressAtAndAfterDisassembly[:dxConfig["uDisassemblyInstructionsAfter"] - 1];
      asHTML += [fsHTMLEncodeAndColorDisassemblyLine(oCdbWrapper, s) for s in asAfterDisassembly];
    elif asHTML:
      asHTML.append("(further disassembly not possible)");
  return "<br/>".join(asHTML);
