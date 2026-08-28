#import <React/RCTBridgeModule.h>

@interface RCT_EXTERN_MODULE(SharedDefaults, NSObject)
RCT_EXTERN_METHOD(getPendingFileName:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
RCT_EXTERN_METHOD(getPendingFileURL:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
RCT_EXTERN_METHOD(clearPendingFileName:(RCTPromiseResolveBlock)resolve
                  rejecter:(RCTPromiseRejectBlock)reject)
@end
