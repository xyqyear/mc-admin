import type { ComponentProps } from 'react'
import { Link } from 'react-router'
import type { VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib/utils'
import { buttonVariants } from '@/shared/ui/button'

export function ButtonLink({
  className,
  variant,
  size,
  ...props
}: ComponentProps<typeof Link> & VariantProps<typeof buttonVariants>) {
  return <Link data-slot="button" className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
