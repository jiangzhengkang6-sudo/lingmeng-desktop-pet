export type ImageFileLike = Pick<File, 'name' | 'type'>

export function isPngFile(file: ImageFileLike) {
  return file.type === 'image/png' || /\.png$/i.test(file.name)
}
