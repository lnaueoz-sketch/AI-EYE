import type { DetectedObject } from '../api/types'
import { labelMeta, pct } from '../lib/format'

interface Props {
  objects: DetectedObject[]
  /** 원본 이미지/영상의 픽셀 크기 (bbox 좌표 기준) */
  width: number
  height: number
  showLabels?: boolean
}

/**
 * 이미지/영상 위에 겹쳐 놓는 SVG.
 * viewBox를 원본 픽셀 크기로 잡아서, 화면에서 몇 px로 보이든 bbox가 자동으로 맞게 늘어남.
 * 부모는 position: relative 이고, 이미지는 object-fit 없이 w-full h-auto 여야 정확히 겹침.
 */
export default function BBoxOverlay({ objects, width, height, showLabels = true }: Props) {
  if (!width || !height) return null
  const stroke = Math.max(2, width / 320)
  const font = Math.max(12, width / 45)

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      {objects.map((o, i) => {
        const [x1, y1, x2, y2] = o.bbox
        const { name, color } = labelMeta(o.label)
        const text = `${name} ${pct(o.confidence)}`
        const tw = text.length * font * 0.62 + 10
        const ty = y1 - font - 6 < 0 ? y1 : y1 - font - 6
        return (
          <g key={i}>
            <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} fill={color} fillOpacity={0.08} stroke={color} strokeWidth={stroke} />
            {showLabels && (
              <>
                <rect x={x1} y={ty} width={tw} height={font + 6} fill={color} />
                <text x={x1 + 5} y={ty + font} fill="#09090b" fontSize={font} fontWeight={700} fontFamily="system-ui, sans-serif">
                  {text}
                </text>
              </>
            )}
          </g>
        )
      })}
    </svg>
  )
}
