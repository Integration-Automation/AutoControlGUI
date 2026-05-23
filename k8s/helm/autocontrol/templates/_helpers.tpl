{{- /*
Shared template helpers — pulled in by every other manifest.
*/ -}}

{{- define "autocontrol.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "autocontrol.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "autocontrol.fullname" -}}
{{- printf "%s-%s-%s" .Release.Name .Chart.Name .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- /*
Fail-fast when the operator hasn't set an auth token. Production
deployments should plug in a sealed secret; the default empty value
exists only so ``helm template`` works during development.
*/ -}}
{{- define "autocontrol.requireToken" -}}
{{- if not .Values.auth.token -}}
{{- fail "auth.token is required. Set it via --set auth.token=... or an external secret." -}}
{{- end -}}
{{- end -}}
