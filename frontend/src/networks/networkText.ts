import { translate } from '../i18n/localization'
import type { MessageId } from '../i18n/localization'
type NetworkKey = Extract<MessageId, `networkLayout.${string}`> extends `networkLayout.${infer Key}` ? Key : never
export const networkText = (key: NetworkKey, values?: Record<string, string | number>) => translate(`networkLayout.${key}`, values)
