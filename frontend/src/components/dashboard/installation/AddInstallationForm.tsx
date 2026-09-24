import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  Loader2,
  MapPin,
  Zap,
  Settings,
  Radio,
  Calendar,
  AlertCircle,
} from 'lucide-react';

interface InstallationFormData {
  name: string;
  ownerName: string;
  ownerContact: string;
  wilaya: string;
  address: string;
  latitude: string;
  longitude: string;
  capacityKwp: string;
  panelCount: string;
  panelModel: string;
  tiltDeg: string;
  azimuthDeg: string;
  inverterModel: string;
  inverterCapacityKw: string;
  commissionedDate: string;
  weatherStation: string;
  degradationRatePercent: string;
  notes: string;
}

const wilayas = [
  'Ariana', 'Béja', 'Ben Arous', 'Bizerte', 'Gabès', 'Gafsa', 'Jendouba',
  'Kairouan', 'Kasserine', 'Kébili', 'Kef', 'Mahdia', 'Manouba', 'Médenine',
  'Monastir', 'Nabeul', 'Sfax', 'Sidi Bouzid', 'Siliana', 'Sousse',
  'Tataouine', 'Tozeur', 'Tunis', 'Zaghouan',
];

const weatherStations = [
  'WS-Tunis-01', 'WS-Tunis-02', 'WS-Sfax-01', 'WS-Sfax-02',
  'WS-Sousse-01', 'WS-Bizerte-01', 'WS-Kairouan-01', 'WS-Nabeul-01',
  'WS-Gabes-01', 'WS-Medenine-01', 'WS-Monastir-01', 'WS-Mahdia-01',
];

const inverterModels = [
  'SMA SB 3.0', 'SMA SB 5.0', 'SMA SB 8.0', 'SMA SB 10.0',
  'SMA STP 15000', 'SMA STP 25000', 'SMA STP 33000',
  'Huawei SUN2000-3KTL', 'Huawei SUN2000-5KTL', 'Huawei SUN2000-10KTL',
  'Fronius Symo 6', 'Fronius Symo 10', 'Fronius Symo 36',
  'ABB TRIO-50', 'ABB TRIO-60', 'ABB TRIO-80',
  'Sungrow SG5KTL', 'Sungrow SG10KTL', 'Sungrow SG25KTL',
];

interface AddInstallationFormProps {
  onSuccess: () => void;
  onCancel?: () => void;
}

export default function AddInstallationForm({
  onSuccess,
  onCancel,
}: AddInstallationFormProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<InstallationFormData>({
    defaultValues: {
      tiltDeg: '30',
      azimuthDeg: '180',
      degradationRatePercent: '0.5',
    },
  });

  // Backend integration point: POST /api/installations with form data
  const onSubmit = async (data: InstallationFormData) => {
    setIsSubmitting(true);
    try {
      await new Promise((r) => setTimeout(r, 1400));
      reset();
      onSuccess();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    reset();
    onCancel?.();
  };

  const FieldError = ({ name }: { name: keyof InstallationFormData }) =>
    errors[name] ? (
      <p className="mt-1 flex items-center gap-1 text-2xs text-[var(--status-critical)]">
        <AlertCircle size={10} />
        {errors[name]?.message as string}
      </p>
    ) : null;

  const Label = ({
    children,
    required,
  }: {
    children: React.ReactNode;
    required?: boolean;
  }) => (
    <label className="mb-1.5 block text-xs font-medium text-foreground">
      {children}
      {required && (
        <span className="ml-0.5 text-[var(--status-critical)]">*</span>
      )}
    </label>
  );

  const Hint = ({ children }: { children: React.ReactNode }) => (
    <p className="mb-1.5 text-2xs text-muted-foreground">{children}</p>
  );

  const inputCls = (hasError?: boolean) =>
    `w-full rounded-lg border bg-muted px-3 py-2 text-xs text-foreground outline-none transition-all duration-150 ${
      hasError
        ? 'border-[var(--status-critical)] focus:border-[var(--status-critical)] focus:ring-2 focus:ring-[var(--status-critical)]/20'
        : 'border-border focus:border-primary/60 focus:ring-2 focus:ring-primary/15'
    }`;

  const SectionHeader = ({
    icon: Icon,
    title,
  }: {
    icon: React.ComponentType<{ size?: number }>;
    title: string;
  }) => (
    <div className="mb-4 flex items-center gap-2">
      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Icon size={13} />
      </span>
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h3>
    </div>
  );

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-8">
      {/* Section 1: Site Information */}
      <div>
        <SectionHeader icon={MapPin} title="Site Information" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label required>Installation Name</Label>
            <Hint>
              Descriptive name for the rooftop site — used in all reports and
              alerts
            </Hint>
            <input
              type="text"
              placeholder="e.g. Villa Sfax Nord — Bloc B"
              className={inputCls(!!errors.name)}
              {...register('name', {
                required: 'Installation name is required',
                minLength: {
                  value: 4,
                  message: 'Name must be at least 4 characters',
                },
              })}
              aria-describedby="name-error"
            />
            <FieldError name="name" />
          </div>

          <div>
            <Label required>Wilaya (Governorate)</Label>
            <select
              className={inputCls(!!errors.wilaya)}
              {...register('wilaya', { required: 'Please select a wilaya' })}
              aria-label="Select wilaya"
            >
              <option value="">Select wilaya…</option>
              {wilayas.map((w) => (
                <option key={`wilaya-${w}`} value={w}>
                  {w}
                </option>
              ))}
            </select>
            <FieldError name="wilaya" />
          </div>

          <div>
            <Label required>Street Address</Label>
            <input
              type="text"
              placeholder="e.g. 12 Rue Ibn Khaldoun, Ariana"
              className={inputCls(!!errors.address)}
              {...register('address', { required: 'Address is required' })}
            />
            <FieldError name="address" />
          </div>

          <div>
            <Label>Latitude (decimal degrees)</Label>
            <Hint>Required for irradiance modeling — e.g. 36.8065</Hint>
            <input
              type="text"
              placeholder="36.8065"
              className={inputCls(!!errors.latitude)}
              {...register('latitude', {
                pattern: {
                  value: /^-?\d{1,3}(\.\d{1,6})?$/,
                  message: 'Enter a valid decimal coordinate',
                },
              })}
            />
            <FieldError name="latitude" />
          </div>

          <div>
            <Label>Longitude (decimal degrees)</Label>
            <Hint>Required for irradiance modeling — e.g. 10.1815</Hint>
            <input
              type="text"
              placeholder="10.1815"
              className={inputCls(!!errors.longitude)}
              {...register('longitude', {
                pattern: {
                  value: /^-?\d{1,3}(\.\d{1,6})?$/,
                  message: 'Enter a valid decimal coordinate',
                },
              })}
            />
            <FieldError name="longitude" />
          </div>
        </div>
      </div>

      {/* Section 2: Owner Details */}
      <div className="border-t border-border/50 pt-8">
        <SectionHeader icon={Settings} title="Owner Details" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label required>Owner Name</Label>
            <input
              type="text"
              placeholder="e.g. Tarek Ben Salah"
              className={inputCls(!!errors.ownerName)}
              {...register('ownerName', { required: 'Owner name is required' })}
            />
            <FieldError name="ownerName" />
          </div>

          <div>
            <Label>Owner Contact</Label>
            <input
              type="text"
              placeholder="+216 XX XXX XXX"
              className={inputCls(!!errors.ownerContact)}
              {...register('ownerContact')}
            />
            <FieldError name="ownerContact" />
          </div>
        </div>
      </div>

      {/* Section 3: PV System Specifications */}
      <div className="border-t border-border/50 pt-8">
        <SectionHeader icon={Zap} title="PV System Specifications" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <Label required>Installed Capacity (kWp)</Label>
            <Hint>Peak kilowatts under standard test conditions</Hint>
            <input
              type="number"
              step="0.1"
              min="0.5"
              max="2000"
              placeholder="12.6"
              className={inputCls(!!errors.capacityKwp)}
              {...register('capacityKwp', {
                required: 'Capacity is required',
                min: { value: 0.5, message: 'Minimum 0.5 kWp' },
                max: { value: 2000, message: 'Maximum 2000 kWp' },
              })}
            />
            <FieldError name="capacityKwp" />
          </div>

          <div>
            <Label>Panel Count</Label>
            <input
              type="number"
              min="1"
              placeholder="32"
              className={inputCls(!!errors.panelCount)}
              {...register('panelCount', {
                min: { value: 1, message: 'Must have at least 1 panel' },
              })}
            />
            <FieldError name="panelCount" />
          </div>

          <div>
            <Label>Panel Model</Label>
            <input
              type="text"
              placeholder="e.g. JA Solar JAM72S30"
              className={inputCls(!!errors.panelModel)}
              {...register('panelModel')}
            />
            <FieldError name="panelModel" />
          </div>

          <div>
            <Label required>Tilt Angle (°)</Label>
            <Hint>Panel inclination from horizontal — typically 20–35° in Tunisia</Hint>
            <input
              type="number"
              min="0"
              max="90"
              step="1"
              placeholder="30"
              className={inputCls(!!errors.tiltDeg)}
              {...register('tiltDeg', {
                required: 'Tilt angle is required',
                min: { value: 0, message: 'Minimum 0°' },
                max: { value: 90, message: 'Maximum 90°' },
              })}
            />
            <FieldError name="tiltDeg" />
          </div>

          <div>
            <Label required>Azimuth Angle (°)</Label>
            <Hint>Panel orientation — 180° = true south, optimal for Tunisia</Hint>
            <input
              type="number"
              min="0"
              max="360"
              step="1"
              placeholder="180"
              className={inputCls(!!errors.azimuthDeg)}
              {...register('azimuthDeg', {
                required: 'Azimuth is required',
                min: { value: 0, message: 'Minimum 0°' },
                max: { value: 360, message: 'Maximum 360°' },
              })}
            />
            <FieldError name="azimuthDeg" />
          </div>

          <div>
            <Label>Annual Degradation Rate (%)</Label>
            <Hint>Expected performance loss per year — typically 0.4–0.7%</Hint>
            <input
              type="number"
              step="0.1"
              min="0"
              max="5"
              placeholder="0.5"
              className={inputCls(!!errors.degradationRatePercent)}
              {...register('degradationRatePercent', {
                min: { value: 0, message: 'Cannot be negative' },
                max: { value: 5, message: 'Maximum 5% per year' },
              })}
            />
            <FieldError name="degradationRatePercent" />
          </div>
        </div>
      </div>

      {/* Section 4: Inverter & Integration */}
      <div className="border-t border-border/50 pt-8">
        <SectionHeader icon={Radio} title="Inverter & Grid Integration" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label required>Inverter Model</Label>
            <select
              className={inputCls(!!errors.inverterModel)}
              {...register('inverterModel', {
                required: 'Inverter model is required',
              })}
              aria-label="Select inverter model"
            >
              <option value="">Select inverter…</option>
              {inverterModels.map((m) => (
                <option key={`inv-${m}`} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <FieldError name="inverterModel" />
          </div>

          <div>
            <Label>Inverter Capacity (kW AC)</Label>
            <input
              type="number"
              step="0.1"
              min="0.5"
              placeholder="10.0"
              className={inputCls(!!errors.inverterCapacityKw)}
              {...register('inverterCapacityKw', {
                min: { value: 0.5, message: 'Minimum 0.5 kW' },
              })}
            />
            <FieldError name="inverterCapacityKw" />
          </div>

          <div>
            <Label required>Nearest Weather Station</Label>
            <Hint>
              Used for irradiance correction and forecast accuracy calibration
            </Hint>
            <select
              className={inputCls(!!errors.weatherStation)}
              {...register('weatherStation', {
                required: 'Weather station assignment is required',
              })}
              aria-label="Select weather station"
            >
              <option value="">Select weather station…</option>
              {weatherStations.map((ws) => (
                <option key={`ws-${ws}`} value={ws}>
                  {ws}
                </option>
              ))}
            </select>
            <FieldError name="weatherStation" />
          </div>

          <div>
            <Label required>Commissioning Date</Label>
            <Hint>Date when the installation was connected to the grid</Hint>
            <input
              type="date"
              className={inputCls(!!errors.commissionedDate)}
              {...register('commissionedDate', {
                required: 'Commissioning date is required',
              })}
            />
            <FieldError name="commissionedDate" />
          </div>
        </div>
      </div>

      {/* Section 5: Notes */}
      <div className="border-t border-border/50 pt-8">
        <SectionHeader icon={Calendar} title="Additional Notes" />
        <div>
          <Label>Operational Notes</Label>
          <Hint>
            Any relevant site information — shading obstructions, maintenance
            history, grid connection type
          </Hint>
          <textarea
            rows={3}
            placeholder="e.g. Partial shading from adjacent building between 14:00–16:00 in winter months…"
            className={`${inputCls()} resize-none`}
            {...register('notes')}
          />
        </div>
      </div>

      {/* Required fields note */}
      <p className="text-2xs text-muted-foreground">
        <span className="text-[var(--status-critical)]">*</span> Required fields
      </p>

      {/* Submit */}
      <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
        <button
          type="button"
          onClick={handleCancel}
          className="rounded-lg border border-border bg-muted px-5 py-2.5 text-xs font-medium text-muted-foreground transition-all duration-150 hover:text-foreground active:scale-95"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="flex min-w-[180px] items-center justify-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground transition-all duration-150 hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70 active:scale-95"
        >
          {isSubmitting ? (
            <>
              <Loader2 size={13} className="animate-spin" />
              Registering…
            </>
          ) : (
            'Register Installation'
          )}
        </button>
      </div>
    </form>
  );
}