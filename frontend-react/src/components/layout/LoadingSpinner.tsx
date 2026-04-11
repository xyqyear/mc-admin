import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  className?: string
  fullscreen?: boolean
  inline?: boolean
  height?: string | number
  /** @deprecated ignored - kept for backward compatibility during migration */
  size?: string
  /** @deprecated ignored - kept for backward compatibility during migration */
  tip?: string
}

export const LoadingSpinner = ({
  className = '',
  fullscreen = false,
  inline = false,
  height,
}: LoadingSpinnerProps) => {
  if (inline) {
    return <Spinner className={cn('size-5', className)} />
  }

  return (
    <div
      className={cn(
        'flex items-center justify-center',
        fullscreen ? 'h-screen' : height ? '' : 'min-h-[400px]',
        className,
      )}
      style={height ? { height } : undefined}
    >
      <Spinner className="size-8" />
    </div>
  )
}

export default LoadingSpinner
