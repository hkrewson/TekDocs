import { translate } from '../i18n/localization'
import { capabilityRegistry, workspaceCapabilities } from '../product/capabilities'
import packageMetadata from '../../package.json'

export default function Overview() {
  return (
    <>
      <header className="page-header"><div><h1>{translate('overview.heading')}</h1><p>TekDocs {packageMetadata.version}</p></div></header>
      <section className="content-section">
        <div className="section-heading"><h2>{translate('overview.areas')}</h2><span>{packageMetadata.version}</span></div>
        <div className="status-table" role="table" aria-label={translate('overview.areas')}>
          {workspaceCapabilities.map((capability) => <div className="status-row" role="row" key={capability}><span role="cell">{capabilityRegistry[capability].label}</span><span role="cell">{translate('overview.available')}</span></div>)}
        </div>
      </section>
    </>
  )
}

