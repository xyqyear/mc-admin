import React, { useState } from 'react'
import { flushSync } from 'react-dom'
import { RotateCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ButtonProps = React.ComponentProps<typeof Button>

interface RefreshButtonProps extends Omit<ButtonProps, 'children' | 'onClick'> {
  isRefreshing?: boolean
  label?: string
  onClick?: () => void | Promise<void>
}

export const RefreshButton: React.FC<RefreshButtonProps> = ({
  isRefreshing = false,
  label = '刷新',
  variant = 'outline',
  onClick,
  disabled,
  ...props
}) => {
  const [pending, setPending] = useState(false)
  const spinning = isRefreshing || pending

  const handleClick = async () => {
    if (!onClick) return
    flushSync(() => setPending(true))
    try {
      await onClick()
    } finally {
      setPending(false)
    }
  }

  return (
    <Button
      variant={variant}
      disabled={disabled || spinning}
      onClick={handleClick}
      {...props}
    >
      <RotateCw className={cn(spinning && 'animate-spin')} />
      {label}
    </Button>
  )
}

export default RefreshButton
