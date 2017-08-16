from dxConfig import dxConfig;
from sBlockHTMLTemplate import sBlockHTMLTemplate;
from sReportHTMLTemplate import sReportHTMLTemplate;
from oVersionInformation import oVersionInformation;

class cBugReport_CdbTerminatedUnexpectedly(object):
  def __init__(oBugReport, oCdbWrapper, uExitCode):
    if uExitCode < 0:
      uExitCode += 1 << 32;
    oBugReport.sBugTypeId = "CdbTerminated:0x%X" % uExitCode;
    oBugReport.sBugDescription = "Cdb terminated unexpectedly";
    oBugReport.sBugLocation = None;
    oBugReport.sSecurityImpact = None;
    oBugReport.oException = None;
    oBugReport.oStack = None;
    
    asBlocksHTML = [];
    
    if oCdbWrapper.bGenerateReportHTML and dxConfig["bLogInReport"]:
      asBlocksHTML.append(sBlockHTMLTemplate % {
        "sName": "Application run log",
        "sCollapsed": "Collapsible", # ...but not Collapsed
        "sContent": oCdbWrapper.sLogHTML,
      });
    oBugReport.sProcessBinaryName = "cdb.exe";
    
    oBugReport.sId = oBugReport.sBugTypeId;
    oBugReport.sStackId = None;
    oBugReport.sBugSourceLocation = None;
    oBugReport.asVersionInformation = ["cBugId: %s" % oVersionInformation.sCurrentVersion];
    # Add Cdb IO to HTML report
    asBlocksHTML.append(sBlockHTMLTemplate % {
      "sName": "Application and cdb output log",
      "sCollapsed": "Collapsed",
      "sContent": oCdbWrapper.sCdbIOHTML
    });
    if oCdbWrapper.bGenerateReportHTML:
      # Create HTML details
      oBugReport.sReportHTML = sReportHTMLTemplate % {
        "sId": oCdbWrapper.fsHTMLEncode(oBugReport.sId),
        "sBugLocation": oCdbWrapper.fsHTMLEncode(oBugReport.sBugLocation or "Unknown"),
        "sOptionalSource": "",
        "sBugDescription": oCdbWrapper.fsHTMLEncode(oBugReport.sBugDescription),
        "sBinaryVersion": "Not available",
        "sSecurityImpact": oBugReport.sSecurityImpact and \
              '<span class="SecurityImpact">%s</span>' % oCdbWrapper.fsHTMLEncode(oBugReport.sSecurityImpact) or "None",
        "sOptionalIntegrityLevel": "",
        "sOptionalApplicationArguments": "",
        "sBugIdVersion": oVersionInformation.sCurrentVersion,
        "sBlocks": "\r\n".join(asBlocksHTML),
        "sCdbStdIO": oCdbWrapper.sCdbIOHTML,
      };
