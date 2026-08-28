import UIKit
import UniformTypeIdentifiers

class ShareViewController: UIViewController {

    private let appGroupId = "group.app.lifeagents.mobile"
    private let appScheme = "lifeagents"

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        handleIncomingFile()
    }

    private func handleIncomingFile() {
        guard let item = extensionContext?.inputItems.first as? NSExtensionItem,
              let attachments = item.attachments else {
            completeRequest()
            return
        }

        let pdfType = UTType.pdf.identifier
        guard let provider = attachments.first(where: { $0.hasItemConformingToTypeIdentifier(pdfType) }) else {
            completeRequest()
            return
        }

        provider.loadItem(forTypeIdentifier: pdfType, options: nil) { [weak self] (data, error) in
            guard let self = self, error == nil else {
                self?.completeRequest()
                return
            }

            var pdfData: Data?
            var fileName = "attachment.pdf"

            if let url = data as? URL {
                fileName = url.lastPathComponent
                pdfData = try? Data(contentsOf: url)
            } else if let raw = data as? Data {
                pdfData = raw
            }

            guard let pdfData = pdfData else {
                self.completeRequest()
                return
            }

            self.savePDFToAppGroup(pdfData, fileName: fileName)
        }
    }

    private func savePDFToAppGroup(_ data: Data, fileName: String) {
        guard let containerURL = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupId
        ) else {
            completeRequest()
            return
        }

        let sharedDir = containerURL.appendingPathComponent("shared_files", isDirectory: true)
        try? FileManager.default.createDirectory(at: sharedDir, withIntermediateDirectories: true)

        let destURL = sharedDir.appendingPathComponent(fileName)
        do {
            if FileManager.default.fileExists(atPath: destURL.path) {
                try FileManager.default.removeItem(at: destURL)
            }
            try data.write(to: destURL)
        } catch {
            completeRequest()
            return
        }

        openMainApp(fileURL: destURL.absoluteString, fileName: fileName)
    }

    private func percentEncode(_ s: String) -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~")
        return s.addingPercentEncoding(withAllowedCharacters: allowed) ?? s
    }

    private func openMainApp(fileURL: String, fileName: String) {
        let urlString = "\(appScheme):///?shareFileURL=\(percentEncode(fileURL))&shareFileName=\(percentEncode(fileName))"
        guard let url = URL(string: urlString) else {
            completeRequest()
            return
        }
        var responder: UIResponder? = self
        while responder != nil {
            if let application = responder as? UIApplication {
                application.open(url)
                break
            }
            responder = responder?.next
        }
        completeRequest()
    }

    private func completeRequest() {
        extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    }
}
