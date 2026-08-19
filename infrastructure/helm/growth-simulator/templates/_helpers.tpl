{{/*
Common labels
*/}}
{{- define "growth-simulator.labels" -}}
app.kubernetes.io/name: growth-simulator
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: grid-resilience
{{- end }}

{{/*
Selector labels
*/}}
{{- define "growth-simulator.selectorLabels" -}}
app.kubernetes.io/name: growth-simulator
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "growth-simulator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default "growth-simulator" .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
