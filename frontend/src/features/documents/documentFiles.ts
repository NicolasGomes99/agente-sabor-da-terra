const textExtensions = new Set(['txt', 'md', 'csv', 'json'])
const mediaExtensions = new Set(['pdf', 'gif', 'jpg', 'jpeg', 'png', 'webp'])

export function fileExtension(filename: string): string {
  const separator = filename.lastIndexOf('.')
  return separator === -1 ? '' : filename.slice(separator + 1).toLowerCase()
}

export function canPreviewDocument(filename: string): boolean {
  const extension = fileExtension(filename)
  return textExtensions.has(extension) || mediaExtensions.has(extension)
}

export function isTextDocument(filename: string): boolean {
  return textExtensions.has(fileExtension(filename))
}

export function saveDownload(blob: Blob, filename: string): void {
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  try {
    link.href = url
    link.download = filename
    document.body.append(link)
    link.click()
  } finally {
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}
