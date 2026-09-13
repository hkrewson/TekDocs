import { translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
type ContractKey = Extract<MessageId, `contractLayout.${string}`> extends `contractLayout.${infer Key}` ? Key : never
export const contractText = (key: ContractKey, values?: Record<string, string | number>) => translate(`contractLayout.${key}`, values)
