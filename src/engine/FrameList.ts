export function parseFrameList(value: string) {
  return [...new Set(
    value
      .split(/[\s,，]+/)
      .filter((item) => item.trim() !== '')
      .map((item) => Number(item))
      .filter((item) => Number.isInteger(item) && item >= 0),
  )]
}