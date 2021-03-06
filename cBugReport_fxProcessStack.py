import hashlib;
from .dxConfig import dxConfig;
from .SourceCodeLinks import fsGetSourceCodeLinkURLForPath;

def cBugReport_fxProcessStack(oBugReport, oCdbWrapper, oProcess, oStack):
  # Get a HTML representation of the stack, find the topmost relevant stack frame and get stack id.
  if oCdbWrapper.bGenerateReportHTML:
    asHTML = [];
    asNotesHTML = [];
  aoStackFramesPartOfId = [];
  # For recursive function loops, the frames in the loop have already been marked as part of the id, and we need to
  # check that none of them are hidden, as that makes no sense. For other exceptions, we still need to mark a few as
  # part of the id, so will need to find out which it is:
  bIdFramesHaveAlreadyBeenMarked = False;
  for oStackFrame in oStack.aoFrames:
    if oStackFrame.sIsHiddenBecause is not None:
      assert not oStackFrame.bIsPartOfId, \
          "Cannot have a hidden frame that is part of the id";
    bIdFramesHaveAlreadyBeenMarked |= oStackFrame.bIsPartOfId;
  # If id frames have not been marked, mark as many as the default settings request. Take into account that hidden
  # frames should not be part of the id.
  if not bIdFramesHaveAlreadyBeenMarked:
    # Mark up to `uStackHashFramesCount` frames as part of the id
    uFramesToBeMarkedCount = dxConfig["uStackHashFramesCount"];
    for oStackFrame in oStack.aoFrames:
      if uFramesToBeMarkedCount == 0:
        break;
      if oStackFrame.sIsHiddenBecause is None and oStackFrame.sId:
        oStackFrame.bIsPartOfId = True;
        uFramesToBeMarkedCount -= 1;
  
  for oStackFrame in oStack.aoFrames:
    if oCdbWrapper.bGenerateReportHTML:
      asFrameHTMLClasses = ["StackFrame"];
      asFrameNotesHTML = [];
      sOptionalSourceHTML = None;
      if oStackFrame.sSourceFilePath:
        sSourceReference = (
          oStackFrame.sSourceFilePath
          + (oStackFrame.uSourceFileLineNumber is not None and (" @ %d" % oStackFrame.uSourceFileLineNumber) or "")
        );
        sSourceReferenceURL = fsGetSourceCodeLinkURLForPath(oStackFrame.sSourceFilePath, oStackFrame.uSourceFileLineNumber);
        if sSourceReferenceURL:
          sOptionalSourceHTML = "[<a href=\"%s\" target=\"_blank\">%s</a>]" % \
              (oCdbWrapper.fsHTMLEncode(sSourceReferenceURL), oCdbWrapper.fsHTMLEncode(sSourceReference));
        else:
          sOptionalSourceHTML = "[%s]" % \
              oCdbWrapper.fsHTMLEncode(sSourceReference);
    if oCdbWrapper.bGenerateReportHTML:
      if oStackFrame.bIsInline:
        # This frame is hidden (because it is irrelevant to the crash)
          asFrameHTMLClasses.append("StackFrameInline");
          asFrameNotesHTML.append("inlined function");
      if oStackFrame.sIsHiddenBecause is not None:
        # This frame is hidden (because it is irrelevant to the crash)
          asFrameHTMLClasses.append("StackFrameHidden");
          asFrameNotesHTML.append(oCdbWrapper.fsHTMLEncode(oStackFrame.sIsHiddenBecause));
      if oStackFrame.bIsPartOfId:
          asFrameHTMLClasses.append("StackFramePartOfId");
          asFrameNotesHTML.append("id: %s" % oCdbWrapper.fsHTMLEncode(oStackFrame.sId));
      if not oStackFrame.oFunction:
        asFrameHTMLClasses.append("StackFrameWithoutSymbol");
        asFrameNotesHTML.append("no function symbol available");
    if oStackFrame.bIsPartOfId:
      aoStackFramesPartOfId.append(oStackFrame);
    if oCdbWrapper.bGenerateReportHTML:
      asHTML.append(" ".join([s for s in [
        "<span class=\"%s\">%s</span>" % (" ".join(asFrameHTMLClasses), oCdbWrapper.fsHTMLEncode(oStackFrame.sAddress)),
        asFrameNotesHTML and "<span class=\"StackFrameNotes\">(%s)</span>" % ", ".join(asFrameNotesHTML),
        sOptionalSourceHTML and "<span class=\"StackFrameSource\">[%s]</span>" % sOptionalSourceHTML,
      ] if s]));
  # Get the stack ids: one that contains all the ids for all stack frames, and one that merges stack ids to fit the
  # requested uStackHashFramesCount.
  asStackIds = [oStackFrame.sId for oStackFrame in aoStackFramesPartOfId];
  oBugReport.sUniqueStackId = ".".join(asStackIds);
  if len(asStackIds) > dxConfig["uStackHashFramesCount"]:
    # There are too many stack hashes: concatinate all excessive hashes togerther with the last non-excessive one and
    # hash them again. This new has replaces them, bringing the number of hashes down to the maximum number. The last
    # hash is effectively a combination of all these hashes, guaranteeing a certain level of uniqueness.
    oHasher = hashlib.md5();
    while len(asStackIds) >= dxConfig["uStackHashFramesCount"]:
      oHasher.update(asStackIds.pop());
    asStackIds.append(oHasher.hexdigest()[:dxConfig["uMaxStackFrameHashChars"]]);
  oBugReport.sStackId = ".".join(asStackIds);
  # Get the bug location.
  oBugReport.sBugLocation = "%s!(unknown)" % oProcess.sSimplifiedBinaryName;
  if aoStackFramesPartOfId:
    oTopIdStackFrame = aoStackFramesPartOfId[0];
    oBugReport.sBugLocation = oTopIdStackFrame.sSimplifiedAddress;
    if oProcess and oTopIdStackFrame.oModule != oProcess.oMainModule:
      # Exception did not happen in the process' binary: add process' binary name to the location:
      oBugReport.sBugLocation = "%s!%s" % (oProcess.sSimplifiedBinaryName, oBugReport.sBugLocation);
    if oTopIdStackFrame.sSourceFilePath:
      oBugReport.sBugSourceLocation = (
        oTopIdStackFrame.sSourceFilePath
        + (oTopIdStackFrame.uSourceFileLineNumber is not None and " @ %d" % oTopIdStackFrame.uSourceFileLineNumber or "")
      );
  if oCdbWrapper.bGenerateReportHTML:
    if oStack.bPartialStack:
      asNotesHTML += ["There were more stack frames than shown above, but these were not considered relevant."];
    sHTML = "".join([
      asHTML      and "<ol>%s</ol>" % "".join(["<li>%s</li>" % s for s in asHTML]) or "",
      asNotesHTML and "<ul>%s</ul>" % "".join(["<li>%s</li>" % s for s in asNotesHTML]) or "",
    ]);
  else:
    sHTML = None;
  return aoStackFramesPartOfId, sHTML;