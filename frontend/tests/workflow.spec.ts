import {test, expect} from '@playwright/test'
import path from 'node:path'

test.beforeEach(async ({page}) => {
  await page.goto('/')
  await page.getByLabel('Contraseña del workspace').fill('e2e-password')
  await page.getByRole('button', {name: 'Entrar al workspace'}).click()
  await expect(page.getByRole('heading', {name: 'Radar de oportunidades'})).toBeVisible()
})

test('dashboard search, evidence, edit and approve with persisted revision', async ({page}) => {
  await page.getByRole('textbox', {name: 'Buscar prospectos'}).fill('Nuvora')
  await expect(page.getByRole('button', {name: 'Ver Nuvora', exact: true})).toBeVisible()
  await page.getByRole('button', {name: 'Ver Nuvora', exact: true}).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Finance Manager', {exact: false})).toBeVisible()
  await dialog.getByRole('button', {name: 'Borrador de correo', exact: true}).click()
  await dialog.getByRole('button', {name: 'Editar borrador'}).click()
  await dialog.getByRole('textbox', {name: 'Asunto del correo'}).fill('Una conversación con Nuvora')
  await dialog.getByRole('button', {name: 'Guardar cambios'}).click()
  await expect(dialog.getByText('Una conversación con Nuvora', {exact: true})).toBeVisible()
  await dialog.getByRole('button', {name: 'Aprobar en HubSpot'}).click()
  await expect(dialog.getByText('Inscrito en «Clara · Primer contacto»')).toBeVisible()
  await page.reload()
  await page.getByRole('button', {name: 'Ver Nuvora', exact: true}).click()
  await expect(page.getByRole('dialog').getByText('Aprobado', {exact: true})).toBeVisible()
})

test('CSV confirms mapping, rejects dirty records and deduplicates', async ({page}) => {
  await page.getByRole('button', {name: 'Importar prospectos'}).click()
  await page.locator('input[type=file]').setInputFiles(path.resolve('public/examples/leads-evento.csv'))
  await expect(page.getByRole('heading', {name: 'Confirma el mapeo'})).toBeVisible()
  await expect(page.getByRole('combobox', {name: 'Columna Empresa *'})).toHaveValue('Nombre empresa')
  await page.getByRole('button', {name: 'Limpiar e iniciar análisis'}).click()
  await expect(page.getByText('Correo personal fuera del perfil B2B.')).toBeVisible()
  await expect(page.getByText('Fuente ya importada.')).toBeVisible()
  await expect(page.getByText('Falta empresa o dominio corporativo válido.')).toBeVisible()
  await expect(page.getByRole('button', {name: 'Vela Systems', exact: false}).first()).toBeVisible()
})

test('Slack inbox exposes routing and review cards', async ({page}) => {
  await page.getByRole('button', {name: /Inbox del SDR/}).first().click()
  await expect(page.getByRole('heading', {name: 'Tu inbox, con contexto.'})).toBeVisible()
  await page.getByRole('button', {name: 'Clara Copilot', exact: true}).click()
  await expect(page.getByText('DM · Sofía Ramírez', {exact: false}).first()).toBeVisible()
  await page.getByRole('button', {name: 'Revisar', exact: true}).first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
})

test('mobile navigation, configuration and audit render without errors', async ({page}) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.setViewportSize({width: 390, height: 844})
  await page.getByRole('button', {name: 'Abrir menú'}).click()
  await page.getByRole('button', {name: 'Configuración', exact: true}).click()
  await page.getByRole('spinbutton', {name: 'Umbral de mensaje directo'}).fill('75')
  await page.getByRole('button', {name: 'Guardar configuración'}).click()
  await expect(page.getByRole('status')).toContainText('Reglas y plantilla guardadas')
  await page.getByRole('button', {name: 'Abrir menú'}).click()
  await page.getByRole('button', {name: 'Actividad', exact: true}).click()
  await expect(page.getByText('Reglas actualizadas', {exact: true}).first()).toBeVisible()
  expect(errors).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

