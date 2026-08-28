import Foundation

@objc(SharedDefaults)
class SharedDefaults: NSObject {

    @objc func getPendingFileName(
        _ resolve: @escaping RCTPromiseResolveBlock,
        rejecter reject: @escaping RCTPromiseRejectBlock
    ) {
        let defaults = UserDefaults(suiteName: "group.app.lifeagents.mobile")
        resolve(defaults?.string(forKey: "pendingShareFileName"))
    }

    @objc func getPendingFileURL(
        _ resolve: @escaping RCTPromiseResolveBlock,
        rejecter reject: @escaping RCTPromiseRejectBlock
    ) {
        let defaults = UserDefaults(suiteName: "group.app.lifeagents.mobile")
        resolve(defaults?.string(forKey: "pendingShareFileURL"))
    }

    @objc func clearPendingFileName(
        _ resolve: @escaping RCTPromiseResolveBlock,
        rejecter reject: @escaping RCTPromiseRejectBlock
    ) {
        let defaults = UserDefaults(suiteName: "group.app.lifeagents.mobile")
        defaults?.removeObject(forKey: "pendingShareFileName")
        defaults?.removeObject(forKey: "pendingShareFileURL")
        resolve(nil)
    }

    @objc static func requiresMainQueueSetup() -> Bool { return false }
}
