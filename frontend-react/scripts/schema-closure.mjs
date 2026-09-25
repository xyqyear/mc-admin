export function selectSchemaClosure(schemas, roots) {
  if (!schemas || typeof schemas !== 'object') throw new Error('OpenAPI components.schemas is missing')
  const selected = {}
  function visitReference(reference) {
    if (!reference.startsWith('#/components/schemas/')) throw new Error(`Unsupported schema reference: ${reference}`)
    const name = reference.slice('#/components/schemas/'.length)
    if (Object.hasOwn(selected, name)) return
    if (!Object.hasOwn(schemas, name)) throw new Error(`Unknown schema reference: ${name}`)
    selected[name] = schemas[name]
    visit(schemas[name], name)
  }
  function visit(node, location) {
    if (!node || typeof node !== 'object' || Array.isArray(node)) throw new Error(`Incomplete schema: ${location}`)
    if (node.$ref) return visitReference(node.$ref)
    const alternatives = node.anyOf ?? node.oneOf ?? node.allOf
    if (alternatives) {
      alternatives.forEach((item, index) => visit(item, `${location}[${index}]`))
      return
    }
    if (!node.type && !node.enum && !Object.hasOwn(node, 'const')) throw new Error(`Unspecified schema type: ${location}`)
    if (node.type === 'object') {
      if (node.additionalProperties === true) throw new Error(`Unspecified additionalProperties: ${location}`)
      if (!node.properties && node.additionalProperties === undefined) throw new Error(`Unspecified object shape: ${location}`)
      for (const [name, property] of Object.entries(node.properties ?? {})) visit(property, `${location}.${name}`)
      if (node.additionalProperties && typeof node.additionalProperties === 'object') visit(node.additionalProperties, `${location}.*`)
    }
    if (node.type === 'array') visit(node.items, `${location}[]`)
  }
  for (const name of roots) visitReference(`#/components/schemas/${name}`)
  return selected
}
