// @ts-expect-error TS6133 - React must be in scope for JSX
import React, { MouseEventHandler } from 'react'
import { Button, ButtonProps } from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlusCircleOutlined,
  CloseOutlined
} from '@ant-design/icons'
import {
  getUiOptions,
  FormContextType,
  IconButtonProps,
  RJSFSchema,
  StrictRJSFSchema,
  TranslatableString
} from '@rjsf/utils'
import { withTheme, ThemeProps } from '@rjsf/core'
import { generateTemplates, generateWidgets } from '@rjsf/antd'

type AntdIconButtonProps<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
> = IconButtonProps<T, S, F> & Pick<ButtonProps, 'block' | 'danger' | 'size'>

function IconButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    iconType = 'default',
    icon,
    onClick,
    uiSchema: _uiSchema,
    registry: _registry,
    color,
    ...otherProps
  } = props
  // Suppress unused variable warnings
  void _uiSchema
  void _registry
  return (
    <Button
      onClick={
        onClick as MouseEventHandler<HTMLAnchorElement> &
          MouseEventHandler<HTMLButtonElement>
      }
      // @ts-expect-error TS2322 - iconType may include values not in ButtonProps['type']
      type={iconType}
      icon={icon}
      color={color as ButtonProps['color']}
      {...otherProps}
    />
  )
}

function AddButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.AddItemButton)}
      iconType="primary"
      block
      {...props}
      icon={<PlusCircleOutlined />}
    />
  )
}

function CopyButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.CopyButton)}
      {...props}
      icon={<CopyOutlined />}
    />
  )
}

function MoveDownButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.MoveDownButton)}
      {...props}
      icon={<ArrowDownOutlined />}
    />
  )
}

function MoveUpButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.MoveUpButton)}
      {...props}
      icon={<ArrowUpOutlined />}
    />
  )
}

function RemoveButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const options = getUiOptions<T, S, F>(props.uiSchema)
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.RemoveButton)}
      danger
      block={!!options.block}
      iconType="primary"
      {...props}
      icon={<DeleteOutlined />}
    />
  )
}

function ClearButton<
  T = any,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = any
>(props: AntdIconButtonProps<T, S, F>) {
  const {
    registry: { translateString }
  } = props
  return (
    <IconButton
      title={translateString(TranslatableString.ClearButton)}
      {...props}
      iconType="link"
      icon={<CloseOutlined />}
    />
  )
}

const baseTemplates = generateTemplates()

const theme: ThemeProps = {
  templates: {
    ...baseTemplates,
    ButtonTemplates: {
      ...baseTemplates.ButtonTemplates,
      AddButton,
      CopyButton,
      MoveDownButton,
      MoveUpButton,
      RemoveButton,
      ClearButton
    }
  },
  widgets: generateWidgets()
}

const ThemedForm = withTheme(theme)

export default ThemedForm
