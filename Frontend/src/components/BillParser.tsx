import React, { useState, useRef } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { 
  Upload, 
  FileImage, 
  CheckCircle, 
  Loader2,
  Edit3,
  Save,
  X
} from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '../utils/supabase/client';

interface ParsedBillData {
  vendor_name: string | null;
  issue_date: string | null;
  due_date: string | null;
  subtotal: number | null;
  tax: number | null;
  tip: number | null;
  total: number | null;
  currency: string | null;
  payment_method: string | null;
  address: string | null;
  category_guess: string | null;
  notes: string | null;
  line_items: Array<{
    name: string;
    quantity: number | null;
    unit_price: number | null;
    line_total: number | null;
  }>;
}

interface BillParserProps {
  onBillParsed?: (data: ParsedBillData) => void;
  onClose?: () => void;
}

export function BillParser({ onBillParsed, onClose }: BillParserProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parsedData, setParsedData] = useState<ParsedBillData | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedData, setEditedData] = useState<ParsedBillData | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setParsedData(null);
    }
  };

  

  const parseBill = async () => {
    if (!selectedFile) return;

    console.log('Starting bill parsing...', selectedFile);
    setIsParsing(true);
    try {
      const formData = new FormData();
      formData.append('image', selectedFile);

      const { data: { session } } = await supabase.auth.getSession();
      console.log('Session:', session);
      if (!session?.access_token) {
        throw new Error('No authentication token');
      }

      console.log('Making API request to parse bill...');
      const response = await fetch('http://localhost:8000/api/parse-bill', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: formData,
      });

      console.log('Response status:', response.status);
      if (!response.ok) {
        const errorData = await response.json();
        console.error('API Error:', errorData);
        throw new Error(errorData.error || 'Failed to parse bill');
      }

      const result = await response.json();
      console.log('Parsed result:', result);
      setParsedData(result.parsed);
      setEditedData(result.parsed);
      toast.success('Bill parsed successfully!');
    } catch (error) {
      console.error('Error parsing bill:', error);
      toast.error(`Failed to parse bill: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsParsing(false);
    }
  };

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleSave = () => {
    if (editedData) {
      setParsedData(editedData);
      setIsEditing(false);
      toast.success('Changes saved!');
    }
  };

  const handleCancel = () => {
    setEditedData(parsedData);
    setIsEditing(false);
  };

  const handleFieldChange = (field: keyof ParsedBillData, value: any) => {
    if (editedData) {
      setEditedData({
        ...editedData,
        [field]: value
      });
    }
  };

  const handleLineItemChange = (index: number, field: string, value: any) => {
    if (editedData) {
      const newLineItems = [...editedData.line_items];
      newLineItems[index] = {
        ...newLineItems[index],
        [field]: field === 'quantity' || field === 'unit_price' || field === 'line_total' 
          ? value === '' ? null : parseFloat(value) 
          : value
      };
      
      // If quantity or unit_price changes, update line_total
      if ((field === 'quantity' || field === 'unit_price') && 
          newLineItems[index].quantity !== null && 
          newLineItems[index].unit_price !== null) {
        newLineItems[index].line_total = 
          (newLineItems[index].quantity || 0) * (newLineItems[index].unit_price || 0);
      }
      
      setEditedData({
        ...editedData,
        line_items: newLineItems
      });
    }
  };

  const handleAddLineItem = () => {
    if (editedData) {
      setEditedData({
        ...editedData,
        line_items: [
          ...editedData.line_items,
          { name: '', quantity: 1, unit_price: 0, line_total: 0 }
        ]
      });
    }
  };

  const handleRemoveLineItem = (index: number) => {
    if (editedData) {
      const newLineItems = [...editedData.line_items];
      newLineItems.splice(index, 1);
      setEditedData({
        ...editedData,
        line_items: newLineItems
      });
    }
  };

  const handleSubmit = () => {
    if (parsedData) {
      onBillParsed?.(parsedData);
      onClose?.();
    }
  };

  return (
    <div className="space-y-6">
      {/* File Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileImage className="h-5 w-5" />
            Upload Bill Image
          </CardTitle>
          <CardDescription>
            Take a photo or upload an image of your receipt or bill
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!previewUrl ? (
            <div className="flex gap-4">
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                className="flex-1"
              >
                <Upload className="h-4 w-4 mr-2" />
                Upload File
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative">
                <img
                  src={previewUrl}
                  alt="Bill preview"
                  className="w-full max-h-64 object-contain border rounded-lg"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  className="absolute top-2 right-2"
                  onClick={() => {
                    setSelectedFile(null);
                    setPreviewUrl(null);
                    setParsedData(null);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Button
                onClick={parseBill}
                disabled={isParsing}
                className="w-full"
              >
                {isParsing ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Parsing Bill...
                  </>
                ) : (
                  <>
                    <FileImage className="h-4 w-4 mr-2" />
                    Parse Bill
                  </>
                )}
              </Button>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileSelect}
            className="hidden"
          />
        </CardContent>
      </Card>

      {/* Parsed Data Display */}
      {parsedData && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-green-600" />
                Parsed Bill Data
              </CardTitle>
              <div className="flex gap-2">
                {!isEditing ? (
                  <Button variant="outline" size="sm" onClick={handleEdit}>
                    <Edit3 className="h-4 w-4 mr-2" />
                    Edit
                  </Button>
                ) : (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={handleCancel}>
                      <X className="h-4 w-4 mr-2" />
                      Cancel
                    </Button>
                    <Button size="sm" onClick={handleSave}>
                      <Save className="h-4 w-4 mr-2" />
                      Save
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Basic Information */}
              <div className="space-y-3">
                <h4 className="font-medium">Basic Information</h4>
                
                <div>
                  <Label htmlFor="vendor">Vendor</Label>
                  {isEditing ? (
                    <Input
                      id="vendor"
                      value={editedData?.vendor_name || ''}
                      onChange={(e) => handleFieldChange('vendor_name', e.target.value)}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {parsedData.vendor_name || 'Not detected'}
                    </p>
                  )}
                </div>

                <div>
                  <Label htmlFor="total">Total Amount</Label>
                  {isEditing ? (
                    <Input
                      id="total"
                      type="number"
                      step="0.01"
                      value={editedData?.total || ''}
                      onChange={(e) => handleFieldChange('total', parseFloat(e.target.value) || null)}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {parsedData.currency} {parsedData.total || 'Not detected'}
                    </p>
                  )}
                </div>

                <div>
                  <Label htmlFor="date">Issue Date</Label>
                  {isEditing ? (
                    <Input
                      id="date"
                      type="date"
                      value={editedData?.issue_date || ''}
                      onChange={(e) => handleFieldChange('issue_date', e.target.value)}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {parsedData.issue_date || 'Not detected'}
                    </p>
                  )}
                </div>

                <div>
                  <Label htmlFor="category">Category</Label>
                  {isEditing ? (
                    <Input
                      id="category"
                      value={editedData?.category_guess || ''}
                      onChange={(e) => handleFieldChange('category_guess', e.target.value)}
                    />
                  ) : (
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">
                        {parsedData.category_guess || 'Unknown'}
                      </Badge>
                    </div>
                  )}
                </div>
              </div>

              {/* Additional Details */}
              <div className="space-y-3">
                <h4 className="font-medium">Additional Details</h4>
                
                <div>
                  <Label>Subtotal</Label>
                  <p className="text-sm text-muted-foreground">
                    {parsedData.currency} {parsedData.subtotal || 'Not detected'}
                  </p>
                </div>

                <div>
                  <Label>Tax</Label>
                  <p className="text-sm text-muted-foreground">
                    {parsedData.currency} {parsedData.tax || 'Not detected'}
                  </p>
                </div>

                <div>
                  <Label>Payment Method</Label>
                  <p className="text-sm text-muted-foreground">
                    {parsedData.payment_method || 'Not detected'}
                  </p>
                </div>

                <div>
                  <Label>Address</Label>
                  <p className="text-sm text-muted-foreground">
                    {parsedData.address || 'Not detected'}
                  </p>
                </div>
              </div>
            </div>

            {/* Line Items */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="font-medium">Line Items</h4>
                {isEditing && (
                  <Button 
                    type="button" 
                    variant="outline" 
                    size="sm"
                    onClick={handleAddLineItem}
                  >
                    + Add Item
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                {(isEditing ? editedData?.line_items : parsedData.line_items)?.map((item, index) => (
                  <div 
                    key={index} 
                    className={`p-3 border rounded ${isEditing ? 'bg-muted/30' : ''}`}
                  >
                    {isEditing ? (
                      <div className="space-y-2">
                        <div className="flex justify-between items-center">
                          <Label htmlFor={`item-name-${index}`} className="text-xs">Item Name</Label>
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="h-6 w-6 text-destructive"
                            onClick={() => handleRemoveLineItem(index)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        <Input
                          id={`item-name-${index}`}
                          value={item.name || ''}
                          onChange={(e) => handleLineItemChange(index, 'name', e.target.value)}
                          placeholder="Item name"
                        />
                        
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <Label htmlFor={`quantity-${index}`} className="text-xs">Quantity</Label>
                            <Input
                              id={`quantity-${index}`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={item.quantity ?? ''}
                              onChange={(e) => handleLineItemChange(index, 'quantity', e.target.value)}
                              placeholder="1"
                            />
                          </div>
                          <div>
                            <Label htmlFor={`unit-price-${index}`} className="text-xs">Unit Price</Label>
                            <div className="relative">
                              <span className="absolute left-3 top-2 text-sm text-muted-foreground">
                                {parsedData.currency || '$'}
                              </span>
                              <Input
                                id={`unit-price-${index}`}
                                type="number"
                                min="0"
                                step="0.01"
                                value={item.unit_price ?? ''}
                                onChange={(e) => handleLineItemChange(index, 'unit_price', e.target.value)}
                                placeholder="0.00"
                                className="pl-10"
                              />
                            </div>
                          </div>
                        </div>
                        
                        <div>
                          <Label htmlFor={`line-total-${index}`} className="text-xs">Line Total</Label>
                          <div className="relative">
                            <span className="absolute left-3 top-2 text-sm text-muted-foreground">
                              {parsedData.currency || '$'}
                            </span>
                            <Input
                              id={`line-total-${index}`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={item.line_total ?? ''}
                              onChange={(e) => handleLineItemChange(index, 'line_total', e.target.value)}
                              placeholder="0.00"
                              className="pl-10 font-medium"
                            />
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <p className="text-sm font-medium">{item.name || 'Unnamed Item'}</p>
                          <p className="text-xs text-muted-foreground">
                            Qty: {item.quantity || '1'} × {parsedData.currency || '$'} 
                            {item.unit_price !== null ? item.unit_price.toFixed(2) : '0.00'}
                          </p>
                        </div>
                        <p className="text-sm font-medium">
                          {parsedData.currency || '$'} {item.line_total !== null ? item.line_total.toFixed(2) : '0.00'}
                        </p>
                      </div>
                    )}
                  </div>
                ))}
                
                {(!parsedData.line_items || parsedData.line_items.length === 0) && !isEditing && (
                  <div className="text-center py-4 text-muted-foreground text-sm">
                    No line items found
                  </div>
                )}
                
                {isEditing && (!editedData?.line_items || editedData.line_items.length === 0) && (
                  <div className="text-center py-4">
                    <Button 
                      type="button" 
                      variant="outline" 
                      onClick={handleAddLineItem}
                    >
                      + Add your first item
                    </Button>
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2 pt-4">
              <Button onClick={handleSubmit} className="flex-1">
                <CheckCircle className="h-4 w-4 mr-2" />
                Add to Expenses
              </Button>
              {onClose && (
                <Button variant="outline" onClick={onClose}>
                  Close
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
