// What the model reads to choose a tool. It fills in the form; our code runs it.
// The tool runs the same calculation as the dashboard screen, so they can't disagree.
export const TOOLS = [
  {
    name: 'leads',
    description:
      'The Leads screen: how many leads came in during a period, compared with the previous stretch of the same length, split by the chosen dimension.',
    input_schema: {
      type: 'object',
      properties: {
        period: { type: 'string', description: 'A year, quarter or month, such as 2026-Q2.' },
        filter: { type: 'array', items: { type: 'string' }, description: 'dimension:value, such as city:Chicago or channel:Instagram.' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'appointments',
    description:
      'The Appointments screen: appointments with a date in the period, in any status, and how many were attended. With filters this screen does not calculate attendance.',
    input_schema: {
      type: 'object',
      properties: { period: { type: 'string' } },
      additionalProperties: false,
    },
  },
]
// There is deliberately no tool for the screen that lists people by name.
// Personal data never reaches the model.
