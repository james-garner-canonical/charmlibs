class SnapError(Exception): pass
class SnapAPIError(SnapError): pass
class SnapNotFoundError(SnapError): pass
class SnapAlreadyInstalledError(SnapError): pass
