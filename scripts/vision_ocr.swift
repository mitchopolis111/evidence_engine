import Foundation
import Vision
import ImageIO

if CommandLine.arguments.count < 2 {
    fputs("usage: vision_ocr.swift image-path\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])

guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fputs("failed to read image: \(imageURL.path)\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.minimumTextHeight = 0.0

let handler = VNImageRequestHandler(cgImage: image, options: [:])

do {
    try handler.perform([request])
} catch {
    fputs("ocr failed: \(error)\n", stderr)
    exit(1)
}

let lines = (request.results ?? []).compactMap { observation in
    observation.topCandidates(1).first?.string
}

print(lines.joined(separator: "\n"))
