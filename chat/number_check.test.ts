import assert from 'node:assert/strict'
import { unsupportedFigures } from './number_check.ts'

const toolResult = '{"total": 1234, "rate": 10.2}'
assert.deepEqual(unsupportedFigures('There were 1,234 leads, 10.2% converted.', [toolResult]), [])
assert.deepEqual(unsupportedFigures('There were 1,500 leads.', [toolResult]), ['1,500'])
assert.deepEqual(unsupportedFigures('About 10% converted.', [toolResult]), ['10'])
console.log('3 of 3 passed')
