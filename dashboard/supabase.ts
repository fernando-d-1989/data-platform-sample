// The only database client in the app.
// Only the public key goes here. The admin key skips the access rules, so it must
// never reach the browser.
//
// The address is written here on purpose, not read from the settings file. An AI
// builder once created an empty second database and rewrote that file. This line
// is the reason the app kept pointing at the real data.
import { createClient } from '@supabase/supabase-js'

const url = 'https://your-project.supabase.co'
const publicKey = 'your-public-key'

export const supabase = createClient(url, publicKey)
